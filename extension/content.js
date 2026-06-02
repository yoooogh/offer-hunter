// Offer 捕手 - 视觉方案：点击 + 全高度展示 + 截图协调
function sleep(ms) { return new Promise(function(r){ setTimeout(r, ms); }); }

function realClick(el) {
  var r = el.getBoundingClientRect();
  var o = { bubbles:true, cancelable:true, view:window, clientX:r.left+r.width/2, clientY:r.top+r.height/2, button:0 };
  el.dispatchEvent(new MouseEvent('mousedown', o));
  el.dispatchEvent(new MouseEvent('mouseup', o));
  el.dispatchEvent(new MouseEvent('click', o));
}

// ===== 全高度 JD 展示（解决截图截不全） =====
// 原理：克隆 JD 容器 → position:fixed → 通过调 top 值实现"滚动"
// 让 popup 多次截图覆盖完整内容

function showFullJD() {
  hideFullJD(); // 先清理旧的

  // 找 JD 容器
  var selectors = [
    '.job-detail', '.job-sec', '.detail-content', '.job-desc',
    '.chat-drawer', '[class*="drawer"]', '[class*="detail-panel"]',
    '[class*="side-panel"]', '.boss-job-detail',
    '.job-detail-wrapper', '[class*="job-detail"]'
  ];
  var container = null;
  for (var i = 0; i < selectors.length; i++) {
    var el = document.querySelector(selectors[i]);
    if (el && el.textContent.trim().length > 80) {
      // 找最合适的：文本长但不是整个页面
      var textLen = el.textContent.trim().length;
      if (textLen > 80 && textLen < 50000) {
        container = el;
        break;
      }
    }
  }
  if (!container) return { height: 0, viewport: 0 };

  // 克隆并清理
  var clone = container.cloneNode(true);
  clone.querySelectorAll(
    'style, script, img, svg, button, iframe, video, audio, input, textarea, select, ' +
    '[class*="btn"], [class*="button"], [class*="icon"], [class*="share"], ' +
    '[class*="close"], [class*="toolbar"], [class*="operation"]'
  ).forEach(function(n) { n.remove(); });

  clone.id = '__offerhunter_jd_full';
  clone.style.cssText =
    'position:fixed;top:0;left:0;width:100vw;height:auto;' +
    'max-height:none;overflow:visible;z-index:2147483647;' +
    'background:#fff;padding:30px 50px;box-sizing:border-box;' +
    'font-size:15px;line-height:1.8;color:#222;';

  document.body.appendChild(clone);

  // 隐藏原页面内容避免干扰
  document.body.style.overflow = 'hidden';

  // 返回尺寸信息
  var totalHeight = clone.scrollHeight;
  var viewportHeight = window.innerHeight;
  return { height: totalHeight, viewport: viewportHeight };
}

// 调整克隆容器的 top 偏移（模拟向下滚动）
function setCloneOffset(offsetY) {
  var clone = document.getElementById('__offerhunter_jd_full');
  if (clone) {
    clone.style.top = '-' + offsetY + 'px';
    return true;
  }
  return false;
}

function hideFullJD() {
  var clone = document.getElementById('__offerhunter_jd_full');
  if (clone) clone.remove();
  document.body.style.overflow = '';
}

// ===== 批量抓取（视觉版） =====
async function batchCollectVision(maxCount) {
  maxCount = maxCount || 20;

  var seen = {};
  var items = [];
  var cards = document.querySelectorAll(
    '.job-card-wrapper, .job-card-box, .job-card-item, ' +
    '[class*="job-card"], [class*="job-item"], .recommend-job-card, li[class*="job"]'
  );

  for (var i = 0; i < cards.length; i++) {
    var links = cards[i].querySelectorAll('a');
    var jobLink = null;
    for (var j = 0; j < links.length; j++) {
      var href = links[j].href || '';
      if ((/job_detail|job_detail\.html|job_detail\//.test(href) || href.indexOf('/job/') > -1) &&
          !/company|employer|brand/.test(href)) {
        jobLink = links[j];
        break;
      }
    }
    if (!jobLink) continue;
    var key = jobLink.pathname || jobLink.href.split('?')[0];
    if (!seen[key]) { seen[key] = true; items.push({ url: jobLink.href, pathname: key }); }
  }
  items = items.slice(0, maxCount);
  console.log('[OH] Found ' + items.length + ' job links');
  if (!items.length) return { count: 0, error: 'no job links found' };

  var jds = [];
  var dedup = {};

  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    console.log('[OH] [' + (i+1) + '/' + items.length + ']');

    var urlId = item.url.split('/').pop().split('?')[0];
    var allJobLinks = document.querySelectorAll('a[href*="job_detail"], a[href*="/job/"]');
    var card = null;
    for (var j = 0; j < allJobLinks.length; j++) {
      if (allJobLinks[j].href.indexOf(urlId) > -1) {
        card = allJobLinks[j].closest('.job-card-wrapper, .job-card-box, .job-card-item, [class*="job-card"], [class*="job-item"], li') || allJobLinks[j];
        break;
      }
    }
    if (!card) { console.log('[OH] skip: card not found'); continue; }

    card.scrollIntoView({ behavior: 'instant', block: 'center' });
    await sleep(300);
    var clickTarget = card.querySelector('a[href*="job_detail"], a[href*="/job/"]') || card;
    realClick(clickTarget);
    await sleep(1500); // 等抽屉打开

    // 展示完整 JD 克隆
    var dims = showFullJD();
    await sleep(300);
    console.log('[OH] JD height=' + dims.height + ' viewport=' + dims.viewport);

    // 通知 popup 截图（popup 会多次截图覆盖全高度）
    var jd = await new Promise(function(resolve) {
      chrome.runtime.sendMessage(
        { type: 'REQUEST_CAPTURE_MULTI', height: dims.height, viewport: dims.viewport },
        function(response) { resolve(response || null); }
      );
    });

    // 清理克隆
    hideFullJD();

    if (jd && jd.title && !dedup[jd.title]) {
      dedup[jd.title] = true;
      jds.push(jd);
      console.log('[OH] OK: ' + jd.title + ' @ ' + jd.company);
    } else if (jd && jd.title) {
      console.log('[OH] dup: ' + jd.title);
    } else {
      console.log('[OH] fail');
    }

    // 关闭抽屉
    var closeBtn = document.querySelector('.chat-close, .dialog-close, [class*="close-btn"], [class*="close"], .icon-close, [class*="drawer"] [class*="close"]');
    if (closeBtn) { realClick(closeBtn); await sleep(600); }
    else {
      var mask = document.querySelector('.mask, .overlay, [class*="mask"], [class*="overlay"]');
      if (mask) { realClick(mask); await sleep(600); }
      else { document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', code:'Escape', keyCode:27, bubbles:true})); await sleep(600); }
    }
    await sleep(500);
  }

  console.log('[OH] Done: ' + jds.length + ' JDs');
  return { count: jds.length, jds: jds };
}

// ===== 消息处理 =====
chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  if (msg.type === 'PING') { sendResponse({ ok: true }); }
  else if (msg.type === 'SHOW_FULL_JD') {
    sendResponse(showFullJD());
  }
  else if (msg.type === 'SET_CLONE_OFFSET') {
    sendResponse({ ok: setCloneOffset(msg.offset || 0) });
  }
  else if (msg.type === 'HIDE_FULL_JD') {
    hideFullJD();
    sendResponse({ ok: true });
  }
  else if (msg.type === 'BATCH_COLLECT_VISION') {
    batchCollectVision(msg.max || 20).then(function(r){ sendResponse(r); }).catch(function(e){ sendResponse({count:0,error:e.message}); });
    return true;
  }
  return true;
});

console.log('[OfferHunter] Vision mode ready');
