// Offer 捕手 - 视觉版 popup (多截图支持)
var collectedJDs = [];
var logLines = [];

(function() {
  chrome.storage.local.get(["cachedJDs"], function(d) {
    if (d.cachedJDs && d.cachedJDs.length > 0) {
      collectedJDs = d.cachedJDs;
      updateUI();
      status("恢复 " + collectedJDs.length + " 个缓存");
    }
  });
})();

function log(msg) {
  logLines.push(msg);
  if (logLines.length > 15) logLines.shift();
  document.getElementById("log").innerHTML = logLines.map(function(l) {
    return '<div style="font-size:10px;color:#666;padding:1px 0">' + l + '</div>';
  }).join("");
}
function status(t) { document.getElementById("status").textContent = t; log(t); }
function saveCache() { chrome.storage.local.set({ cachedJDs: collectedJDs }); }

function updateUI() {
  document.getElementById("count").textContent = collectedJDs.length;
  saveCache();
  var html = collectedJDs.map(function(jd, i) {
    return '<div style="font-size:10px;padding:3px 0;border-bottom:1px solid #f5f5f5;display:flex;justify-content:space-between">' +
      '<span style="flex:1">' + (i+1) + '. ' + (jd.title||"??").slice(0,45) + ' @ ' + (jd.company||"??").slice(0,15) + '</span>' +
      '<span style="cursor:pointer;color:#6366f1;font-size:10px;white-space:nowrap" data-idx="' + i + '">📋</span>' +
      '</div>';
  }).join("");
  if (collectedJDs.length > 0) {
    html += '<div style="margin-top:6px"><button id="btn-copy-all" style="width:100%;font-size:10px;padding:4px;border:1px solid #d9d9d9;border-radius:4px;cursor:pointer;background:#fff">📋 复制全部</button></div>';
  }
  document.getElementById("jd-list").innerHTML = html;
  document.querySelectorAll("[data-idx]").forEach(function(el) {
    el.addEventListener("click", function(e) { e.stopPropagation(); copyJD(parseInt(el.dataset.idx)); });
  });
  var ca = document.getElementById("btn-copy-all");
  if (ca) ca.addEventListener("click", copyAllJDs);
}

function copyJD(idx) {
  var jd = collectedJDs[idx];
  var text = "【岗位名称】" + (jd.title||"") + "\n【公司】" + (jd.company||"") + "\n【岗位JD】\n" + (jd.jd||"");
  navigator.clipboard.writeText(text).then(function() { status("已复制: " + (jd.title||"").slice(0,20)); });
}
function copyAllJDs() {
  var text = collectedJDs.map(function(jd,i) { return (i+1) + ". " + (jd.title||"") + " @ " + (jd.company||"") + "\n" + jd.jd; }).join("\n\n---\n\n");
  navigator.clipboard.writeText(text).then(function() { status("已复制全部 " + collectedJDs.length + " 个"); });
}

// ===== 多截图 → Flask VL API =====
async function captureMultiAndExtract(tab, totalHeight, viewportHeight) {
  var server = "https://offer-hunter-production.up.railway.app";
  var images = [];
  var offset = 0;
  var overlap = 120; // 像素重叠避免切断文字
  var step = viewportHeight - overlap;
  if (step < 200) step = viewportHeight; // 极小视口保护

  while (offset < totalHeight) {
    // 通知 content script 调整克隆的 top
    try {
      await chrome.tabs.sendMessage(tab.id, { type: 'SET_CLONE_OFFSET', offset: offset });
    } catch(e) {}
    await new Promise(function(r) { setTimeout(r, 250); });

    // 截图（失败自动重试一次）
    var dataUrl = null;
    for (var retry = 0; retry < 2; retry++) {
      try {
        dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 70 });
        break;
      } catch(e) {
        if (retry === 1) { log("截图失败: " + e.message); break; }
        await new Promise(function(r) { setTimeout(r, 500); });
      }
    }
    if (!dataUrl) break;
    images.push(dataUrl);

    offset += step;
    if (images.length >= 6) break; // 最多 6 张，防止无限循环
  }

  if (!images.length) return null;

  log("🤖 发送 " + images.length + " 张截图给 VL...");
  try {
    var resp = await fetch(server + "/api/jd/vision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ images: images })
    });
    var result = await resp.json();
    if (result.ok) {
      log("✅ " + (result.jd.title||"").slice(0,30) + " @ " + (result.jd.company||""));
      return result.jd;
    } else {
      log("❌ VL: " + (result.error || "unknown"));
      return null;
    }
  } catch(e) {
    log("❌ 服务器: " + e.message);
    return null;
  }
}

// ===== 监听 content script 的截图请求（批量模式） =====
chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  if (msg.type === 'REQUEST_CAPTURE_MULTI') {
    log("📸 收到多截图请求 (JD高" + msg.height + "px)");
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
      if (!tabs.length) { sendResponse(null); return; }
      captureMultiAndExtract(tabs[0], msg.height, msg.viewport).then(function(jd) {
        sendResponse(jd || {});
      });
    });
    return true; // 异步
  }
});

// ===== 📄 抓取当前 =====
document.getElementById("btn-current").addEventListener("click", async function() {
  status("截图中...");
  var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tabs.length) { status("找不到标签页"); return; }
  var tab = tabs[0];

  // 展示完整 JD 克隆
  var dims = { height: 0, viewport: 0 };
  try {
    dims = await chrome.tabs.sendMessage(tab.id, { type: 'SHOW_FULL_JD' });
  } catch(e) {
    status("请刷新BOSS页面后重试");
    return;
  }

  if (!dims.height) {
    status("未检测到JD区域");
    return;
  }

  log("JD高度: " + dims.height + "px 视口: " + dims.viewport + "px");

  // 多截图 + VL
  var jd = await captureMultiAndExtract(tab, dims.height, dims.viewport);

  // 清理
  try { await chrome.tabs.sendMessage(tab.id, { type: 'HIDE_FULL_JD' }); } catch(e) {}

  if (jd) {
    collectedJDs.push(jd);
    updateUI();
    status("✅ " + (jd.title||"").slice(0,30));
  } else {
    status("❌ 识别失败，请重试");
  }
});

// ===== 📦 批量抓取 =====
document.getElementById("btn-batch").addEventListener("click", async function() {
  status("批量抓取中...");
  var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tabs.length) { status("找不到标签页"); return; }
  var tab = tabs[0];

  try { await chrome.tabs.sendMessage(tab.id, { type: "PING" }); }
  catch(e) { status("请刷新BOSS页面"); return; }

  var result = await chrome.tabs.sendMessage(tab.id, { type: "BATCH_COLLECT_VISION", max: 20 });
  if (result && result.count > 0) {
    collectedJDs = result.jds;
    updateUI();
    status("完成: " + result.count + " 个岗位");
  } else if (result && result.error) {
    status(result.error);
  } else {
    status("未获取到JD");
  }
});

// ===== 🗑 清空 =====
document.getElementById("btn-clear").addEventListener("click", function() {
  collectedJDs = [];
  updateUI();
  status("已清空");
});
