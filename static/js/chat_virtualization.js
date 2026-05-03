/**
 * Vanilla virtual scroller + message list budget helpers for live chat.
 * Exposes: window.ChatVirtualization
 */
(function (global) {
  "use strict";

  var DEFAULT_ROW = 84;
  var DEFAULT_OVERSCAN = 6;
  var MAX_MSG_NODES = 200;

  function rafThrottle(fn) {
    var scheduled = false;
    var lastArgs;
    return function () {
      lastArgs = arguments;
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(function () {
        scheduled = false;
        fn.apply(null, lastArgs);
      });
    };
  }

  /**
   * Fixed-height virtual list: only visible rows (+ overscan) stay in the DOM.
   */
  function createFixedVirtualList(options) {
    var scrollEl = options.scrollEl;
    var rowHeight = options.rowHeight || DEFAULT_ROW;
    var overscan = typeof options.overscan === "number" ? options.overscan : DEFAULT_OVERSCAN;
    var getCount = options.getCount;
    var renderRowAt = options.renderRowAt;

    var inner = document.createElement("div");
    inner.className = "cls3741_vscroll_inner";
    inner.style.position = "relative";
    inner.style.minHeight = "0";

    var rowPool = new Map();

    function clearRows() {
      rowPool.forEach(function (el) {
        try {
          el.remove();
        } catch (e) {}
      });
      rowPool.clear();
    }

    function sync() {
      var count = getCount() || 0;
      var totalHeight = Math.max(0, count * rowHeight);
      inner.style.height = totalHeight + "px";

      if (count === 0) {
        clearRows();
        return;
      }

      var st = scrollEl.scrollTop;
      var ch = scrollEl.clientHeight || 0;
      var start;
      var end;
      // If height isn't measurable yet (hidden panel / first paint), don't cap to overscan-only (was showing 6 of 10).
      if (ch < rowHeight) {
        start = 0;
        end = count;
      } else {
        start = Math.max(0, Math.floor(st / rowHeight) - overscan);
        end = Math.min(count, Math.ceil((st + ch) / rowHeight) + overscan);
      }

      rowPool.forEach(function (el, idx) {
        if (idx < start || idx >= end) {
          try {
            el.remove();
          } catch (e) {}
          rowPool.delete(idx);
        }
      });

      for (var i = start; i < end; i++) {
        if (rowPool.has(i)) continue;
        var el = renderRowAt(i);
        el.style.boxSizing = "border-box";
        el.style.position = "absolute";
        el.style.left = "0";
        el.style.right = "0";
        el.style.top = i * rowHeight + "px";
        el.style.minHeight = rowHeight + "px";
        inner.appendChild(el);
        rowPool.set(i, el);
      }
    }

    var onScroll = rafThrottle(sync);

    /** Full redraw of visible rows — required when row *data* changes (unread, snippet). */
    function refreshFromData() {
      clearRows();
      sync();
    }

    scrollEl.innerHTML = "";
    scrollEl.appendChild(inner);
    scrollEl.addEventListener("scroll", onScroll, { passive: true });
    sync();

    return {
      refresh: refreshFromData,
      scrollToIndex: function (idx) {
        var count = getCount() || 0;
        if (count <= 0) return;
        var i = Math.max(0, Math.min(idx, count - 1));
        scrollEl.scrollTop = i * rowHeight;
        sync();
      },
      destroy: function () {
        scrollEl.removeEventListener("scroll", onScroll);
        clearRows();
        if (inner.parentNode === scrollEl) scrollEl.removeChild(inner);
      },
      getInner: function () {
        return inner;
      },
    };
  }

  function pruneOldestMessages(container, maxNodes) {
    if (!container || !maxNodes) return;
    var max = maxNodes;
    var nodes = container.children;
    while (nodes.length > max) {
      var first = nodes[0];
      if (first && first.id === "cls3741_chat_load_older_sentinel") {
        if (nodes.length <= 1) break;
        first = nodes[1];
      }
      if (first) first.remove();
      else break;
    }
  }

  global.ChatVirtualization = {
    DEFAULT_CONTACT_ROW_HEIGHT: DEFAULT_ROW,
    DEFAULT_OVERSCAN: DEFAULT_OVERSCAN,
    MAX_MESSAGE_NODES: MAX_MSG_NODES,
    rafThrottle: rafThrottle,
    createFixedVirtualList: createFixedVirtualList,
    pruneOldestMessages: pruneOldestMessages,
  };
})(typeof window !== "undefined" ? window : this);
