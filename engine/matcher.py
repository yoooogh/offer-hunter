"""Offer 捕手 - 匹配引擎"""
import json, re, urllib.request

class MatchEngine:
    def __init__(self, api_key: str):
        self.key = api_key
        self.api = "https://api.deepseek.com/v1/chat/completions"

    def call(self, prompt: str, max_tokens: int = 3000) -> str:
        body = json.dumps({
            "model": "deepseek-chat", "max_tokens": max_tokens, "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()
        req = urllib.request.Request(self.api, data=body, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {self.key}"
        })
        resp = urllib.request.urlopen(req, timeout=120)
        return json.loads(resp.read())["choices"][0]["message"]["content"]

    # ===== 简历解析 =====
    def parse_resume(self, text: str) -> dict:
        prompt = f"解析简历为JSON:\n{text}\n\n格式:{{\"name\":\"\",\"phone\":\"\",\"email\":\"\",\"education\":[{{\"school\":\"\",\"degree\":\"\",\"major\":\"\",\"start\":\"\",\"end\":\"\"}}],\"skills\":[],\"work\":[{{\"company\":\"\",\"role\":\"\",\"start\":\"\",\"end\":\"\",\"desc\":\"\"}}],\"summary\":\"一句话总结\"}}"
        resp = self.call(prompt, 2000)
        m = re.search(r'\{[\s\S]*\}', resp)
        return json.loads(m.group(0)) if m else {}

    # ===== JD 解析 =====
    def parse_jd(self, text: str) -> dict:
        prompt = (
            "提取以下JD的关键信息。输出纯JSON(不要markdown包裹):\n"
            + text[:3000] + "\n\n"
            "格式:{\"title\":\"岗位名\",\"company\":\"公司名\",\"industry\":\"行业\","
            "\"requirements\":{\"education\":\"学历\",\"major\":\"专业\",\"experience\":\"经验\",\"skills\":[]},"
            "\"responsibilities\":[],\"nice_to_have\":[],\"keywords\":[]}\n"
            "如果某字段JD没写,填\"\"。公司名如果在JD中没有,从上下文推测或填\"未知\"。"
        )
        try:
            resp = self.call(prompt, 1500)
            # 处理可能的 markdown 代码块
            resp = resp.replace("```json", "").replace("```", "")
            m = re.search(r'\{[\s\S]*\}', resp)
            if m:
                jd = json.loads(m.group(0))
                if jd.get("title"):
                    return jd
        except:
            pass
        # 降级：手动提取基本信息
        lines = text.strip().split("\n")
        return {
            "title": lines[0][:80] if lines else "未知岗位",
            "company": "",
            "industry": "",
            "requirements": {"education": "", "major": "", "experience": "", "skills": []},
            "responsibilities": [],
            "nice_to_have": [],
            "keywords": [],
            "raw": text
        }

    # ===== 批量匹配 =====
    def batch_match(self, resume: dict, jds: list) -> list:
        results = []
        BATCH = 10
        for i in range(0, len(jds), BATCH):
            batch = jds[i:i+BATCH]
            scored = self._match_batch(resume, batch)
            results.extend(scored)
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def _match_batch(self, resume: dict, jds: list) -> list:
        profile = json.dumps(resume, ensure_ascii=False)
        jd_text = "\n".join(f"岗位{i+1}: {j.get('title','')} 公司:{j.get('company','')}\n要求:{json.dumps(j.get('requirements',{}),ensure_ascii=False)}\n职责:{json.dumps(j.get('responsibilities',[]),ensure_ascii=False)}" for i,j in enumerate(jds))

        prompt = (
            "你是招聘匹配专家。给每个岗位打分。\n"
            "总分(0-100) = 经验匹配(0-40)+学科兼容(0-25)+技能覆盖(0-15)+公司匹配(0-10)+综合适配(0-10)\n"
            "学科分七类:商科/理科/工科/文科/医科/艺术/其他。同大类正常打分,跨大类≤10。\n"
            "技能是加分项不是及格线。\n"
            "输出分析+优点+不足+建议。\n"
            f"候选人:\n{profile}\n\n{jd_text}\n\n"
            '输出JSON:[{"index":1,"score":75,"exp":30,"hard":20,"skill":10,"company":8,"fit":7,"analysis":"一句话","strength":"优点","weakness":"不足","suggestion":"建议"}]'
        )
        resp = self.call(prompt, 4000)
        m = re.search(r'\[[\s\S]*\]', resp)
        scores = json.loads(m.group(0)) if m else []

        return [
            {**jds[i], "score": s.get("score", 50), "exp": s.get("exp", 0),
             "hard": s.get("hard", 0), "skill": s.get("skill", 0),
             "company_score": s.get("company", 0), "fit": s.get("fit", 0),
             "analysis": s.get("analysis", ""), "strength": s.get("strength", ""),
             "weakness": s.get("weakness", ""), "suggestion": s.get("suggestion", "")}
            for i, s in enumerate(scores)
        ]

    # ===== 公司偏好分析 =====
    def analyze_preferences(self, resume: dict, jds: list) -> dict:
        """分析每家公司的隐形偏好，并分组给出建议"""
        profile = json.dumps(resume, ensure_ascii=False)
        jd_summary = "\n".join(
            f"岗位{i+1}: {j.get('title','')} @ {j.get('company','')}\n"
            f"职责:{json.dumps(j.get('responsibilities',[]),ensure_ascii=False)[:200]}\n"
            f"要求:{json.dumps(j.get('requirements',{}),ensure_ascii=False)[:200]}"
            for i,j in enumerate(jds)
        )
        prompt = (
            "你是企业招聘偏好分析师。一家公司 JD 的写法会暴露它的隐形用人标准。\n\n"
            f"候选人背景:\n{profile}\n\n"
            f"岗位列表:\n{jd_summary}\n\n"
            "对每个岗位判断公司的用人偏好，从以下维度打分(0-10):\n"
            "school_weight: 院校层级权重(10=极端看重985/211)\n"
            "intern_weight: 实习经历权重(10=没有对口实习直接挂)\n"
            "skill_weight: 技能匹配权重(10=技能不对口完全没戏)\n"
            "cert_weight: 证书/资质权重(10=没证过不了筛)\n"
            "language_weight: 语言/海外背景权重\n\n"
            "然后把这些公司按偏好模式分成2-4组，每组给不同的策略建议。\n\n"
            "输出JSON:\n"
            '{"companies":[{"index":1,"school":7,"intern":8,"skill":5,"cert":3,"lang":2,'
            '"pattern":"实习驱动型","advice":"该岗看重实习经验多于院校"}],'
            '"groups":[{"name":"实习驱动型","companies":[1,2,5],"analysis":"分析",'
            '"strategy":"针对这类公司的简历策略","risk":"你的风险点"}]}'
        )
        resp = self.call(prompt, 3000)
        m = re.search(r'\{[\s\S]*\}', resp)
        return json.loads(m.group(0)) if m else {}

    # ===== 公司分析 =====
    def analyze_company(self, company_name: str, industry_hint: str = "") -> dict:
        prompt = (
            f"分析这家公司:\n公司:{company_name}\n行业线索:{industry_hint}\n\n"
            "输出JSON:{\"industry\":\"行业\",\"scale\":\"规模\",\"stage\":\"发展阶段\","
            "\"pros\":[\"对候选人的优势\"],\"cons\":[\"需要注意的风险\"],"
            "\"fit_score\":0-10,\"fit_reason\":\"一句话\"}"
        )
        try:
            resp = self.call(prompt, 1000)
            m = re.search(r'\{[\s\S]*\}', resp)
            return json.loads(m.group(0)) if m else {}
        except:
            return {}

    # ===== 深度诊断 =====
    def deep_diagnose(self, resume: dict, jd: dict) -> dict:
        prompt = (
            f"逐项对比简历和JD，给出诊断:\n简历:{json.dumps(resume,ensure_ascii=False)}\nJD:{json.dumps(jd,ensure_ascii=False)}\n\n"
            "输出JSON:\n{\"overall_score\":75,\"checks\":[{\"item\":\"检查项\",\"status\":\"pass/warn/fail\",\"detail\":\"说明\",\"fix\":\"修改建议\"}],"
            "\"optimized_resume\":\"优化后的简历文本（不编造事实，只优化表达和结构）\",\"interview_questions\":[\"预测面试问题\"]}"
        )
        resp = self.call(prompt, 4000)
        m = re.search(r'\{[\s\S]*\}', resp)
        return json.loads(m.group(0)) if m else {}

    # ===== 简历优化 =====
    def optimize_resume(self, resume: dict, target_jds: list) -> dict:
        jd_text = json.dumps(target_jds[:5], ensure_ascii=False)
        prompt = (
            f"你是职业规划师。分析候选人目前简历与目标岗位的差距，给出成长路线图。\n\n"
            f"候选人:\n{json.dumps(resume,ensure_ascii=False)}\n\n"
            f"目标岗位(共性分析):\n{jd_text}\n\n"
            "从这些岗位中提取共性要求，对比候选人现状，找出能力差距。\n"
            "不要改写简历！给出候选人还需要补充什么。\n\n"
            "输出JSON:\n"
            '{"overall_rating":"当前竞争力评级(A/B/C/D)",'
            '"gap_analysis":[{"gap":"能力缺口","current":"现在",'
            '"target":"需要达到","severity":"high/medium/low"}],'
            '"roadmap":{"short_term":[{"action":"投递前可做","detail":"具体行动"}],'
            '"mid_term":[{"action":"3个月内可做","detail":"具体行动"}],'
            '"long_term":[{"action":"职业发展方向","detail":"具体行动"}]}}'
        )
        resp = self.call(prompt, 3000)
        m = re.search(r'\{[\s\S]*\}', resp)
        return json.loads(m.group(0)) if m else {}
