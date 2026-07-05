"""Offer 捕手 - 匹配引擎"""
import json, re, urllib.request

class MatchEngine:
    def __init__(self, api_key: str, api_url: str = "", api_model: str = ""):
        self.key = api_key
        self.api = api_url or "https://api.deepseek.com/v1/chat/completions"
        self.model = api_model or "deepseek-chat"

    def call(self, prompt: str, max_tokens: int = 3000) -> str:
        body = json.dumps({
            "model": self.model, "max_tokens": max_tokens, "temperature": 0.3,
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
    def batch_match(self, resume: dict, jds: list, weights: dict = None) -> list:
        if weights is None:
            weights = {"exp": 40, "hard": 25, "skill": 15, "company": 10, "fit": 10}
        results = []
        BATCH = 5
        for i in range(0, len(jds), BATCH):
            batch = jds[i:i+BATCH]
            scored = self._match_batch(resume, batch, weights)
            results.extend(scored)
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def _match_batch(self, resume: dict, jds: list, weights: dict) -> list:
        profile = json.dumps(resume, ensure_ascii=False)
        jd_text = "\n".join(f"岗位{i+1}: {j.get('title','')} 公司:{j.get('company','')}\n要求:{json.dumps(j.get('requirements',{}),ensure_ascii=False)}\n职责:{json.dumps(j.get('responsibilities',[]),ensure_ascii=False)}" for i,j in enumerate(jds))

        w = weights
        prompt = (
            "你是招聘匹配专家。给每个岗位严格按以下维度打分。\n"
            f"总分(0-100) = 经验匹配(0-{w['exp']})+学科兼容(0-{w['hard']})+技能覆盖(0-{w['skill']})+公司匹配(0-{w['company']})+综合适配(0-{w['fit']})\n"
            f"重要: 每个维度的分数不得超过该维度的满分({w['exp']}/{w['hard']}/{w['skill']}/{w['company']}/{w['fit']})。\n"
            "学科分七类:商科/理科/工科/文科/医科/艺术/其他。同大类正常打分,跨大类≤10。\n"
            "技能是加分项不是及格线。\n"
            "每个岗位输出分析+优点+不足+建议。\n"
            "⚠️ 必须拉开差距: 高匹配度岗位 80-95分, 中匹配度 60-79分, 低匹配度 30-59分。不要所有岗位给出相近分数。\n"
            f"候选人:\n{profile}\n\n{jd_text}\n\n"
            '输出JSON:[{"index":1,"score":0,"exp":0,"hard":0,"skill":0,"company":0,"fit":0,"analysis":"一句话","strength":"优点","weakness":"不足","suggestion":"建议"}]'
        )
        resp = self.call(prompt, 4000)
        m = re.search(r'\[[\s\S]*\]', resp)
        scores = json.loads(m.group(0)) if m else []

        return self._validate_scores(scores, jds, weights)

    def _validate_scores(self, scores: list, jds: list, weights: dict) -> list:
        """校验 AI 返回的分数是否合理，异常则降级处理"""
        results = []
        for i, s in enumerate(scores):
            exp = s.get("exp", 0)
            hard = s.get("hard", 0)
            skill = s.get("skill", 0)
            company = s.get("company", 0)
            fit = s.get("fit", 0)
            score = s.get("score", 0)

            # 各维度不超过满分
            exp = min(exp, weights.get("exp", 40))
            hard = min(hard, weights.get("hard", 25))
            skill = min(skill, weights.get("skill", 15))
            company = min(company, weights.get("company", 10))
            fit = min(fit, weights.get("fit", 10))

            # 各维度不低于0
            exp = max(exp, 0); hard = max(hard, 0); skill = max(skill, 0)
            company = max(company, 0); fit = max(fit, 0)

            # 总分修正：如果 AI 给的总分和五维之和偏差过大，用五维之和
            dim_sum = exp + hard + skill + company + fit
            if abs(score - dim_sum) > 5:
                score = dim_sum

            # 总分裁剪
            score = max(0, min(100, score))

            results.append({
                **jds[i],
                "score": score, "exp": exp, "hard": hard,
                "skill": skill, "company_score": company, "fit": fit,
                "analysis": s.get("analysis", ""), "strength": s.get("strength", ""),
                "weakness": s.get("weakness", ""), "suggestion": s.get("suggestion", ""),
            })
        return results

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

    # ===== 深度诊断（硬性过滤+软性匹配+逐项比对） =====
    def deep_diagnose(self, resume: dict, jd_text: str) -> dict:
        prompt = (
            "你是资深HR。按以下流程完成岗位匹配诊断。\n\n"
            "【步骤1】从JD中提取各项要求，按规则分类:\n"
            "硬性要求信号(一项不达标=该岗基本没戏): \"要求\"、\"必须\"、\"需\"、\"及以上\"、\"至少X年\"、\"熟练掌握/精通\"\n"
            "软性偏好信号(不达标扣分但不淘汰): \"优先\"、\"加分\"、\"了解即可\"、\"有...经验优先\"、\"熟悉...更好\"\n"
            "兜底规则: 学历+经验年限永远是硬性。执业资格证书(CPA/律师证/执业医师等)→硬性, 其他证书→软性。\n"
            "如果一句话的主句是\"要求\"但附带\"优先\"→主句动词决定(通常是硬性)。\n\n"
            "【步骤2】逐项比对简历，每项输出:\n"
            "- item: 检查项名称\n"
            "- category: \"硬性\"或\"软性\"\n"
            "- status: \"pass\"(达标) / \"warn\"(软性不满足) / \"fail\"(硬性不达标)\n"
            "- jd_require: JD要求什么\n"
            "- resume_has: 简历现状\n"
            "- suggestion: 告诉候选人差在哪、怎么补救\n"
            "- fix: 具体的修改建议(修改简历/补充经历/降级投递)\n\n"
            "【步骤3】汇总:\n"
            "计分规则:\n"
            "- 硬性不达标=0项 → 正常打分70-95 (各项软性正常加减分)\n"
            "- 硬性不达标=1项 → 困难45-69\n"
            "- 硬性不达标≥2项 → 不建议<45\n"
            "给出替代建议: 如果综合评分低，建议候选人投递什么更匹配的岗位方向。\n"
            "最后给出优化后的简历文本(不编造事实，只优化表达和结构)+预测面试问题(中英文，3-5个)。\n\n"
            f"候选人简历:\n{json.dumps(resume, ensure_ascii=False)}\n\n"
            f"目标岗位JD:\n{jd_text[:4000]}\n\n"
            "输出JSON(不要markdown包裹):\n"
            '{"jd_breakdown":{"hard":[{"item":"学历","requirement":"硕士及以上"}],"soft":[{"item":"B端经验","requirement":"有B端经验优先"}]},'
            '"checks":[{"item":"学历","category":"硬性","status":"fail","jd_require":"硕士及以上","resume_has":"本科",'
            '"suggestion":"该岗硬性要求硕士。如有硕士在读经历请补充；否则该岗过不了简历关。","fix":"建议查看同公司本科可投的同类岗位"}],'
            '"hard_fail_count":0,"verdict":"可冲","overall_score":0,'
            '"alternative_suggestions":[],'
            '"optimized_resume":"优化后的简历文本","interview_questions":["面试问题1"]}'
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
