/**
 * AI Sales Copilot — 3-column workspace (history | chat | rules).
 */
(function () {
  var messagesEl = document.getElementById("aiCoachingMessages");
  var inputEl = document.getElementById("aiCoachingInput");
  var sendBtn = document.getElementById("aiCoachingSend");
  var loadingEl = document.getElementById("aiCoachingLoading");
  var showRulesBtn = document.getElementById("aiCoachingShowRules");
  var clearRulesBtn = document.getElementById("aiCoachingClearRules");
  var voiceBtn = document.getElementById("aiCopilotVoice");
  var fileBtn = document.getElementById("aiCopilotFile");
  var fileInput = document.getElementById("aiCopilotFileInput");
  var copilotRoot = document.getElementById("dashCopilot");
  var mainInnerEl = document.getElementById("aiCopilotMainInner");
  var emptyStateEl = document.getElementById("aiCopilotEmptyState");
  var chatFlowEl = document.getElementById("aiCopilotChatFlow");
  var suggestionsEl = document.getElementById("aiCopilotSuggestions");
  var newChatBtn = document.getElementById("aiCopilotNewChat");
  var historySearchEl = document.getElementById("aiCopilotHistorySearch");
  var historyListEl = document.getElementById("aiCopilotHistoryList");
  var rulesListEl = document.getElementById("aiCopilotRulesList");
  var personaValueEl = document.getElementById("aiCopilotPersonaValue");
  var rulesSettingsBtn = document.getElementById("aiCopilotRulesSettings");
  var attachmentsEl = document.getElementById("aiCopilotAttachments");

  var coachingMessages = [];
  var coachRulesBlockEl = null;
  var currentRulesList = [];
  var canCoach = true;
  var recognition = null;
  var recognizing = false;
  var chatSessions = [];
  var activeSessionId = null;
  var activeConversationId = null;
  var pendingNewChat = false;
  var currentPersona = "Friendly Consultant";
  var historySearchQuery = "";
  var pendingAttachment = null;
  var conversationsLoading = false;

  var VIDEO_MAX_BYTES = 16 * 1024 * 1024;
  var IMAGE_MAX_BYTES = 8 * 1024 * 1024;
  var AUDIO_MAX_BYTES = 16 * 1024 * 1024;
  var TEXT_MAX_BYTES = 5 * 1024 * 1024;

  var PRESET_RULES = [
  { label: "Suggest Upsell Items", text: "When a customer buys one item, suggest one complementary upsell item." },
  { label: "Lead with Featured Product", text: "Always lead with our featured product and mention limited stock when the customer hesitates." },
  { label: "Handle Price Objections", text: "If the customer objects on price, offer a small bundle discount and highlight value." },
  { label: "Warm Short Replies", text: "Be warmer and shorter in replies while staying persuasive." }
  ];

  if (copilotRoot && copilotRoot.getAttribute("data-can-coach") === "false") {
    canCoach = false;
  }

  function getChannelId() {
    var el = document.getElementById("current_channel_id");
    if (el && el.value) return el.value;
    if (typeof window.currentChannelId !== "undefined" && window.currentChannelId) {
      return window.currentChannelId;
    }
    if (
      typeof window.TEMPLATE_CONFIG !== "undefined" &&
      window.TEMPLATE_CONFIG.initialChannelId &&
      window.TEMPLATE_CONFIG.initialChannelId !== "null"
    ) {
      return window.TEMPLATE_CONFIG.initialChannelId;
    }
    return null;
  }

  function csrfToken() {
    return (document.querySelector("[name=csrfmiddlewaretoken]") || {}).value || "";
  }

  function truncate(text, max) {
    var t = String(text || "").trim();
    if (t.length <= max) return t;
    return t.slice(0, max - 1) + "…";
  }

  function formatFileSize(bytes) {
    var n = Number(bytes) || 0;
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / (1024 * 1024)).toFixed(1) + " MB";
  }

  function getFileCategory(file) {
    var mime = (file.type || "").toLowerCase();
    if (mime.indexOf("image/") === 0) return "image";
    if (mime.indexOf("video/") === 0) return "video";
    if (mime.indexOf("audio/") === 0) return "audio";
    return "text";
  }

  function validateCoachFile(file) {
    var cat = getFileCategory(file);
    if (cat === "video" && file.size > VIDEO_MAX_BYTES) {
      return {
        ok: false,
        message: "Video must be 16 MB or smaller (WhatsApp limit).",
      };
    }
    if (cat === "image" && file.size > IMAGE_MAX_BYTES) {
      return { ok: false, message: "Images must be 8 MB or smaller." };
    }
    if (cat === "audio" && file.size > AUDIO_MAX_BYTES) {
      return { ok: false, message: "Audio must be 16 MB or smaller." };
    }
    if (cat === "text" && file.size > TEXT_MAX_BYTES) {
      return { ok: false, message: "Documents must be 5 MB or smaller." };
    }
    return { ok: true, category: cat };
  }

  function serializeMessageForSession(m) {
    var o = { role: m.role, content: m.content };
    if (m.attachment) {
      o.attachment = {
        type: m.attachment.type,
        name: m.attachment.name,
        size: m.attachment.size,
        mime: m.attachment.mime,
      };
    }
    return o;
  }

  function revokeAttachmentPreview(att) {
    if (att && att.previewUrl) {
      try {
        URL.revokeObjectURL(att.previewUrl);
      } catch (e) {}
    }
  }

  function clearPendingAttachment() {
    if (pendingAttachment) revokeAttachmentPreview(pendingAttachment);
    pendingAttachment = null;
    renderAttachmentTray();
  }

  function renderAttachmentTray() {
    if (!attachmentsEl) return;
    attachmentsEl.innerHTML = "";
    if (!pendingAttachment) {
      attachmentsEl.hidden = true;
      return;
    }
    attachmentsEl.hidden = false;
    var card = document.createElement("div");
    card.className = "ai-chat-attach-card";

    var preview = document.createElement("div");
    preview.className = "ai-chat-attach-preview";
    if (pendingAttachment.type === "image" && pendingAttachment.previewUrl) {
      var img = document.createElement("img");
      img.src = pendingAttachment.previewUrl;
      img.alt = pendingAttachment.name || "Image";
      preview.appendChild(img);
    } else if (pendingAttachment.type === "video" && pendingAttachment.previewUrl) {
      var vid = document.createElement("video");
      vid.src = pendingAttachment.previewUrl;
      vid.muted = true;
      vid.playsInline = true;
      preview.appendChild(vid);
    } else if (pendingAttachment.type === "audio") {
      preview.classList.add("is-audio");
      preview.innerHTML = '<i class="fas fa-music"></i>';
    } else {
      preview.classList.add("is-file");
      preview.innerHTML = '<i class="fas fa-file-alt"></i>';
    }

    var meta = document.createElement("div");
    meta.className = "ai-chat-attach-meta";
    var name = document.createElement("div");
    name.className = "ai-chat-attach-name";
    name.textContent = pendingAttachment.name || "File";
    var sub = document.createElement("div");
    sub.className = "ai-chat-attach-sub";
    sub.textContent =
      (pendingAttachment.type || "file").toUpperCase() + " · " + formatFileSize(pendingAttachment.size);
    meta.appendChild(name);
    meta.appendChild(sub);

    var removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "ai-chat-attach-remove";
    removeBtn.title = "Remove attachment";
    removeBtn.innerHTML = '<i class="fas fa-times"></i>';
    removeBtn.addEventListener("click", function () {
      clearPendingAttachment();
    });

    card.appendChild(preview);
    card.appendChild(meta);
    card.appendChild(removeBtn);
    attachmentsEl.appendChild(card);
  }

  function renderMessageAttachment(bubble, attachment) {
    if (!attachment || !bubble) return;
    var wrap = document.createElement("div");
    wrap.className = "ai-chat-msg-attachment";
    if (attachment.type === "image" && attachment.previewUrl) {
      var img = document.createElement("img");
      img.src = attachment.previewUrl;
      img.alt = attachment.name || "Image";
      wrap.appendChild(img);
    } else if (attachment.type === "video" && attachment.previewUrl) {
      var video = document.createElement("video");
      video.src = attachment.previewUrl;
      video.controls = true;
      video.playsInline = true;
      wrap.appendChild(video);
    } else if (attachment.type === "audio" && attachment.previewUrl) {
      var audio = document.createElement("audio");
      audio.src = attachment.previewUrl;
      audio.controls = true;
      wrap.appendChild(audio);
    } else {
      wrap.className = "ai-chat-msg-file-card";
      var icon = document.createElement("i");
      icon.className =
        attachment.type === "audio"
          ? "fas fa-music"
          : attachment.type === "video"
            ? "fas fa-video"
            : "fas fa-file-alt";
      var label = document.createElement("span");
      label.textContent = attachment.name || "Attachment";
      wrap.appendChild(icon);
      wrap.appendChild(label);
    }
    bubble.appendChild(wrap);
  }

  function defaultTextForAttachment(att, userText) {
    if (userText) return userText;
    if (!att) return "";
    if (att.type === "image") return "Please review this image for sales coaching.";
    if (att.type === "video") return "I've shared a video — please review it for sales coaching.";
    if (att.type === "audio") return "Please review this audio message.";
    if (att.type === "text") return "Please review this document for persuasion / sales rules.";
    return "";
  }

  function buildAttachmentPayload(att) {
    if (!att) return null;
    var payload = {
      type: att.type,
      name: att.name,
      size: att.size,
      mime: att.mime,
    };
    if (att.type === "text") {
      payload.text_content = att.textContent || "";
    } else if (att.type !== "video" && att.dataBase64) {
      payload.data = att.dataBase64;
    }
    return payload;
  }

  function cloneAttachmentForMessage(att) {
    if (!att) return null;
    return {
      type: att.type,
      name: att.name,
      size: att.size,
      mime: att.mime,
      previewUrl: att.previewUrl || null,
    };
  }

  function processSelectedFile(file) {
    var check = validateCoachFile(file);
    if (!check.ok) {
      appendMessage("assistant", check.message);
      return;
    }
    clearPendingAttachment();
    var category = check.category;
    var att = {
      type: category,
      name: file.name,
      size: file.size,
      mime: file.type || "",
      previewUrl: null,
      textContent: null,
      dataBase64: null,
    };
    if (category === "image" || category === "video" || category === "audio") {
      att.previewUrl = URL.createObjectURL(file);
    }
    pendingAttachment = att;

    if (category === "text") {
      var textReader = new FileReader();
      textReader.onload = function () {
        var text = String(textReader.result || "").trim();
        if (!text) {
          appendMessage("assistant", "Could not read this file.");
          clearPendingAttachment();
          return;
        }
        if (text.length > 8000) text = text.slice(0, 8000);
        pendingAttachment.textContent = text;
        renderAttachmentTray();
        if (inputEl) inputEl.focus();
      };
      textReader.onerror = function () {
        appendMessage("assistant", "Could not read this file.");
        clearPendingAttachment();
      };
      textReader.readAsText(file);
      return;
    }

    if (category === "image" || category === "audio") {
      var binReader = new FileReader();
      binReader.onload = function () {
        var result = String(binReader.result || "");
        var comma = result.indexOf(",");
        pendingAttachment.dataBase64 = comma >= 0 ? result.slice(comma + 1) : "";
        renderAttachmentTray();
        if (inputEl) inputEl.focus();
      };
      binReader.onerror = function () {
        appendMessage("assistant", "Could not read this file.");
        clearPendingAttachment();
      };
      binReader.readAsDataURL(file);
      return;
    }

    renderAttachmentTray();
    if (inputEl) inputEl.focus();
  }

  function getConvoFromUrl() {
    try {
      return new URLSearchParams(window.location.search).get("convo");
    } catch (e) {
      return null;
    }
  }

  function setConvoInUrl(convoId, replace) {
    try {
      var url = new URL(window.location.href);
      if (convoId) url.searchParams.set("convo", convoId);
      else url.searchParams.delete("convo");
      if (replace) history.replaceState({ copilotConvo: convoId || null }, "", url);
      else history.pushState({ copilotConvo: convoId || null }, "", url);
    } catch (e) {}
  }

  function isPageReload() {
    try {
      var nav = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
      return !!(nav && nav.type === "reload");
    } catch (e) {
      return false;
    }
  }

  function mapConversationToSession(conv) {
    return {
      id: conv.id,
      title: conv.title || "New chat",
      createdAt: conv.created_at,
      updatedAt: conv.updated_at,
      messageCount: conv.message_count || 0,
      messages: [],
    };
  }

  function fetchConversationsList(cid) {
    return fetch(
      "/discount/whatssapAPI/api/admin/coach-ai-conversations/?channel_id=" + encodeURIComponent(cid)
    ).then(function (r) {
      return r.json();
    });
  }

  function createConversationOnServer(cid, title) {
    return fetch("/discount/whatssapAPI/api/admin/coach-ai-conversations/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({
        channel_id: parseInt(cid, 10) || cid,
        title: title || "New chat",
      }),
    }).then(function (r) {
      return r.json();
    });
  }

  function fetchConversationMessages(conversationId) {
    return fetch(
      "/discount/whatssapAPI/api/admin/coach-ai-history/?conversation_id=" + encodeURIComponent(conversationId)
    ).then(function (r) {
      return r.json();
    });
  }

  function refreshConversationsList(cid, keepActiveId) {
    return fetchConversationsList(cid).then(function (data) {
      var list = (data.conversations || []).map(mapConversationToSession);
      chatSessions = list;
      if (keepActiveId && chatSessions.some(function (s) { return s.id === keepActiveId; })) {
        activeSessionId = keepActiveId;
      }
      renderHistoryList();
      return list;
    });
  }

  function activateConversation(conversationId, options) {
    options = options || {};
    var cid = getChannelId();
    if (!cid || !conversationId) return Promise.resolve(false);
    activeConversationId = conversationId;
    activeSessionId = conversationId;
    pendingNewChat = false;
    setConvoInUrl(conversationId, options.replaceUrl !== false);

    if (options.empty) {
      coachingMessages = [];
      renderMessagesFromState();
      renderHistoryList();
      return Promise.resolve(true);
    }

    updateCopilotLayout({ loading: true });
    return fetchConversationMessages(conversationId)
      .then(function (data) {
        coachingMessages = (data.messages || []).map(function (m) {
          return { role: m.role, content: m.content };
        });
        renderMessagesFromState();
        renderHistoryList();
        loadRulesPanel();
        return true;
      })
      .catch(function () {
        coachingMessages = [];
        renderMessagesFromState();
        appendMessage("assistant", "Could not load this conversation.");
        return false;
      });
  }

  function createAndActivateNewConversation(cid) {
    return createConversationOnServer(cid, "New chat").then(function (data) {
      if (!data.success || !data.conversation) {
        throw new Error(data.error || "Could not create conversation");
      }
      var session = mapConversationToSession(data.conversation);
      chatSessions.unshift(session);
      activeConversationId = session.id;
      activeSessionId = session.id;
      pendingNewChat = false;
      coachingMessages = [];
      setConvoInUrl(session.id, true);
      renderMessagesFromState();
      renderHistoryList();
      return session;
    });
  }

  function personaStorageKey() {
    return "ai_copilot_persona_" + (getChannelId() || "none");
  }

  function loadPersonaFromStorage() {
    try {
      var saved = localStorage.getItem(personaStorageKey());
      if (saved) currentPersona = saved;
    } catch (e) {}
    if (personaValueEl) personaValueEl.textContent = currentPersona;
  }

  function savePersonaToStorage() {
    try {
      localStorage.setItem(personaStorageKey(), currentPersona);
    } catch (e) {}
    if (personaValueEl) personaValueEl.textContent = currentPersona;
  }

  function setPersona(name) {
    if (!name) return;
    currentPersona = name;
    savePersonaToStorage();
  }

  function getActiveSession() {
    for (var i = 0; i < chatSessions.length; i++) {
      if (chatSessions[i].id === activeSessionId) return chatSessions[i];
    }
    return null;
  }

  function isDraftNewChat() {
    return pendingNewChat && coachingMessages.length === 0;
  }

  function sessionTitleFromMessages(messages) {
    for (var i = 0; i < messages.length; i++) {
      if (messages[i].role === "user" && messages[i].content) {
        return truncate(messages[i].content, 42);
      }
    }
    return "New chat";
  }

  function updateActiveSessionFromMessages() {
    if (!coachingMessages.length || !activeConversationId) return;
    var session = getActiveSession();
    if (session) {
      session.title = sessionTitleFromMessages(
        coachingMessages.map(serializeMessageForSession)
      );
      session.updatedAt = new Date().toISOString();
      renderHistoryList();
    }
  }

  function switchToSession(sessionId) {
    if (!sessionId || sessionId === activeConversationId) return;
    hideRules();
    activateConversation(sessionId, { replaceUrl: false });
  }

  function startNewChat() {
    if (!canCoach) return;
    var cid = getChannelId();
    if (!cid) {
      appendMessage("assistant", "Select a channel first.");
      return;
    }
    if (isDraftNewChat()) {
      if (inputEl) inputEl.focus();
      return;
    }
    hideRules();
    clearPendingAttachment();
    if (inputEl) inputEl.value = "";
    createAndActivateNewConversation(cid).then(function () {
      if (inputEl) inputEl.focus();
    }).catch(function () {
      appendMessage("assistant", "Could not start a new conversation.");
    });
  }

  function isSameDay(a, b) {
    return (
      a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() &&
      a.getDate() === b.getDate()
    );
  }

  function historyGroupLabel(date) {
    var now = new Date();
    var yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    if (isSameDay(date, now)) return "Today";
    if (isSameDay(date, yesterday)) return "Yesterday";
    return "Earlier";
  }

  function renderHistoryList() {
    if (!historyListEl) return;
    historyListEl.innerHTML = "";
    var q = (historySearchQuery || "").toLowerCase().trim();
    var filtered = chatSessions.filter(function (s) {
      if (!q) return true;
      return (s.title || "").toLowerCase().indexOf(q) !== -1;
    });
    if (!filtered.length) {
      historyListEl.innerHTML = '<div class="dash-copilot-history-empty">No chats yet. Start a new conversation.</div>';
      return;
    }
    var groups = { Today: [], Yesterday: [], Earlier: [] };
    filtered.forEach(function (s) {
      var label = historyGroupLabel(new Date(s.updatedAt || s.createdAt));
      groups[label].push(s);
    });
    ["Today", "Yesterday", "Earlier"].forEach(function (label) {
      if (!groups[label].length) return;
      var group = document.createElement("div");
      group.className = "dash-copilot-history-group";
      var heading = document.createElement("div");
      heading.className = "dash-copilot-history-group-label";
      heading.textContent = label;
      group.appendChild(heading);
      groups[label].forEach(function (session) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "dash-copilot-history-item";
        if (session.id === activeSessionId) btn.classList.add("is-active");
        btn.textContent = session.title || "New chat";
        btn.addEventListener("click", function () {
          switchToSession(session.id);
        });
        group.appendChild(btn);
      });
      historyListEl.appendChild(group);
    });
  }

  function setLoading(on) {
    if (loadingEl) {
      loadingEl.style.display = on ? "block" : "none";
      loadingEl.classList.toggle("is-on", !!on);
    }
    var blocked = !canCoach || !!on;
    if (sendBtn) sendBtn.disabled = blocked;
    if (inputEl) inputEl.disabled = blocked;
  }

  function isEmptyChat() {
    return coachingMessages.length === 0;
  }

  function updateCopilotLayout(opts) {
    opts = opts || {};
    var loading = !!opts.loading;
    var isEmpty = !loading && isEmptyChat();

    if (mainInnerEl) {
      mainInnerEl.classList.toggle("is-empty", isEmpty);
      mainInnerEl.classList.toggle("is-chat", !isEmpty);
    }
    if (emptyStateEl) emptyStateEl.hidden = !isEmpty;
    if (chatFlowEl) chatFlowEl.hidden = isEmpty;
    if (suggestionsEl) suggestionsEl.hidden = !isEmpty;
    if (window.syncCopilotNewChatBtn) window.syncCopilotNewChatBtn();
  }

  function scrollMessages() {
    if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function renderMessagesFromState() {
    if (!messagesEl) return;
    coachRulesBlockEl = null;
    messagesEl.innerHTML = "";
    updateCopilotLayout();
    if (!coachingMessages.length) {
      return;
    }
    coachingMessages.forEach(function (m, idx) {
      appendMessage(m.role, m.content, idx, m.attachment, m.ui_component, m.component_data);
    });
    scrollMessages();
  }

  function appendRichText(container, text) {
    var str = String(text || "");
    if (!str) return;
    var re = /\*\*(.+?)\*\*/g;
    var last = 0;
    var match;
    var found = false;
    while ((match = re.exec(str)) !== null) {
      found = true;
      if (match.index > last) {
        container.appendChild(document.createTextNode(str.slice(last, match.index)));
      }
      var strong = document.createElement("strong");
      strong.className = "dash-msg-emphasis";
      strong.textContent = match[1];
      container.appendChild(strong);
      last = re.lastIndex;
    }
    if (!found) {
      container.appendChild(document.createTextNode(str));
      return;
    }
    if (last < str.length) {
      container.appendChild(document.createTextNode(str.slice(last)));
    }
  }

  function stripMarkdownBold(text) {
    return String(text || "").replace(/\*\*(.+?)\*\*/g, "$1");
  }

  function looksLikeMetricLine(line) {
    var t = (line || "").trim();
    if (!t) return false;
    if (/^\|/.test(t) || /^\s*\|?[\s:|-]+$/.test(t)) return true;
    if (/[:：]\s+\S+/.test(t) && /[\d%$]|orders?|rate|product|conversion|saved|contacts|ai\b/i.test(t)) return true;
    if (/\b\d+(\.\d+)?%\b/.test(t) && t.length < 90) return true;
    return false;
  }

  function splitAssistantContent(text) {
    var lines = String(text || "").split("\n");
    var parts = [];
    var buf = [];
    var bufType = "text";
    function flush() {
      var joined = buf.join("\n").replace(/^\n+|\n+$/g, "");
      if (joined.trim()) parts.push({ type: bufType, text: joined });
      buf = [];
    }
    lines.forEach(function (line) {
      var nextType = looksLikeMetricLine(line) ? "card" : "text";
      if (buf.length && nextType !== bufType) flush();
      bufType = nextType;
      buf.push(line);
    });
    flush();
    return parts.length ? parts : [{ type: "text", text: String(text || "") }];
  }

  function renderDataCard(text) {
    var card = document.createElement("div");
    card.className = "dash-msg-data-card bg-gray-900/50 rounded-xl";
    var rows = text.split("\n").map(function (l) { return l.trim(); }).filter(Boolean);
    var tableRows = rows.filter(function (l) { return l.indexOf("|") !== -1 && !/^[\s|:|-]+$/.test(l); });
    if (tableRows.length >= 2) {
      var table = document.createElement("table");
      tableRows.forEach(function (row, i) {
        var cells = row.split("|").map(function (c) { return c.trim(); }).filter(Boolean);
        var tr = document.createElement("tr");
        cells.forEach(function (cell) {
          var el = document.createElement(i === 0 ? "th" : "td");
          if (i === 0) {
            el.textContent = stripMarkdownBold(cell);
          } else {
            el.className = "dash-msg-emphasis";
            appendRichText(el, cell);
          }
          tr.appendChild(el);
        });
        table.appendChild(tr);
      });
      card.appendChild(table);
      return card;
    }
    rows.forEach(function (line) {
      var metric = document.createElement("div");
      metric.className = "dash-msg-metric";
      var parts = line.split(/[:：]/);
      var label = document.createElement("span");
      label.className = "dash-msg-metric-label";
      var value = document.createElement("span");
      value.className = "dash-msg-metric-value";
      if (parts.length >= 2) {
        label.textContent = stripMarkdownBold(parts.shift()).replace(/^\*+|\*+$/g, "").trim();
        value.className = "dash-msg-metric-value dash-msg-emphasis";
        appendRichText(value, parts.join(":").trim());
      } else {
        label.textContent = stripMarkdownBold(line);
        value.textContent = "";
      }
      metric.appendChild(label);
      if (value.textContent) metric.appendChild(value);
      card.appendChild(metric);
    });
    return card;
  }

  function bindAssistantActions(wrap, content, msgIndex) {
    wrap.addEventListener("click", function (e) {
      var btn = e.target.closest(".dash-msg-action");
      if (!btn || !wrap.contains(btn)) return;
      var action = btn.getAttribute("data-action");
      if (action === "copy") {
        var text = content || "";
        var done = function () {
          btn.classList.add("is-active");
          var prev = btn.innerHTML;
          btn.innerHTML = '<i class="fas fa-check"></i>';
          setTimeout(function () {
            btn.classList.remove("is-active");
            btn.innerHTML = prev;
          }, 1200);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done).catch(done);
        } else {
          done();
        }
        return;
      }
      if (action === "regenerate") {
        regenerateFrom(msgIndex);
        return;
      }
      if (action === "like" || action === "dislike") {
        var other = wrap.querySelector('.dash-msg-action[data-action="' + (action === "like" ? "dislike" : "like") + '"]');
        var on = !btn.classList.contains("is-active");
        wrap.querySelectorAll('.dash-msg-action[data-action="like"], .dash-msg-action[data-action="dislike"]').forEach(function (b) {
          b.classList.remove("is-active");
        });
        if (on) btn.classList.add("is-active");
        if (other && !on) other.classList.remove("is-active");
      }
    });
  }

  function renderStatusBadge(componentData) {
    var badge = document.createElement("div");
    var type = (componentData && componentData.type) || "success";
    badge.className = "dash-copilot-status-badge dash-copilot-status-badge--" + type;
    badge.textContent = (componentData && componentData.text) || "Updated";
    return badge;
  }

  function renderStructuredTable(componentData) {
    var card = document.createElement("div");
    card.className = "dash-msg-data-card bg-gray-900/50 rounded-xl";
    if (componentData && componentData.title) {
      var title = document.createElement("div");
      title.className = "dash-msg-data-card-title";
      title.textContent = componentData.title;
      card.appendChild(title);
    }
    (componentData && componentData.rows ? componentData.rows : []).forEach(function (row) {
      var metric = document.createElement("div");
      metric.className = "dash-msg-metric";
      var label = document.createElement("span");
      label.className = "dash-msg-metric-label";
      label.textContent = row.label || "";
      var value = document.createElement("span");
      value.className = "dash-msg-metric-value dash-msg-emphasis";
      appendRichText(value, row.value || "");
      metric.appendChild(label);
      metric.appendChild(value);
      card.appendChild(metric);
    });
    return card;
  }

  function appendStructuredUi(bubble, uiComponent, componentData) {
    if (!uiComponent || uiComponent === "none" || !componentData) return;
    if (uiComponent === "status_badge") {
      bubble.appendChild(renderStatusBadge(componentData));
      return;
    }
    if (uiComponent === "data_table") {
      bubble.appendChild(renderStructuredTable(componentData));
    }
  }

  function appendMessage(role, content, msgIndex, attachment, uiComponent, componentData) {
    if (!messagesEl) return;
    updateCopilotLayout();
    var hint = messagesEl.querySelector(".dash-copilot-empty");
    if (hint) hint.remove();
    if (msgIndex == null) msgIndex = Math.max(0, coachingMessages.length - 1);
    if (attachment == null && coachingMessages[msgIndex]) {
      attachment = coachingMessages[msgIndex].attachment;
    }

    var wrap = document.createElement("div");
    wrap.className = "dash-msg ai-coaching-msg " + role;
    wrap.dataset.index = String(msgIndex);

    var avatar = document.createElement("span");
    avatar.className = "dash-msg-avatar";
    avatar.innerHTML = role === "user" ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';

    var col = document.createElement("div");
    col.className = "dash-msg-col";

    var bubble = document.createElement("div");
    bubble.setAttribute("dir", "auto");
    if (role === "user") {
      bubble.className = "dash-msg-body bg-gray-700/50 rounded-3xl rounded-tr-sm max-w-[75%] px-6 py-4";
      if (attachment) renderMessageAttachment(bubble, attachment);
      if (content) {
        var userText = document.createElement("div");
        userText.className = "dash-msg-text";
        userText.textContent = content;
        bubble.appendChild(userText);
      }
      col.appendChild(bubble);
    } else {
      bubble.className = "dash-msg-body bg-indigo-500/10 rounded-3xl rounded-tl-sm max-w-[85%] px-6 py-4";
      var parts = splitAssistantContent(content);
      parts.forEach(function (part) {
        if (part.type === "card") {
          bubble.appendChild(renderDataCard(part.text));
        } else {
          var prose = document.createElement("div");
          prose.className = "dash-msg-text";
          prose.setAttribute("dir", "auto");
          appendRichText(prose, part.text);
          bubble.appendChild(prose);
        }
      });
      appendStructuredUi(bubble, uiComponent, componentData);
      var toolbar = document.createElement("div");
      toolbar.className = "dash-msg-toolbar";
      toolbar.innerHTML =
        '<button type="button" class="dash-msg-action text-gray-500" data-action="copy" title="Copy"><i class="far fa-copy"></i></button>' +
        '<button type="button" class="dash-msg-action text-gray-500" data-action="regenerate" title="Regenerate"><i class="fas fa-rotate"></i></button>' +
        '<button type="button" class="dash-msg-action text-gray-500" data-action="like" title="Good response"><i class="far fa-thumbs-up"></i></button>' +
        '<button type="button" class="dash-msg-action text-gray-500" data-action="dislike" title="Bad response"><i class="far fa-thumbs-down"></i></button>';
      col.appendChild(bubble);
      col.appendChild(toolbar);
      bindAssistantActions(wrap, content, msgIndex);
    }
    wrap.appendChild(avatar);
    wrap.appendChild(col);
    messagesEl.appendChild(wrap);
    scrollMessages();
  }

  function regenerateFrom(msgIndex) {
    if (!canCoach) return;
    var i = parseInt(msgIndex, 10);
    if (isNaN(i) || i < 0) return;
    var userIdx = i - 1;
    while (userIdx >= 0 && coachingMessages[userIdx] && coachingMessages[userIdx].role !== "user") userIdx--;
    if (userIdx < 0) return;
    coachingMessages = coachingMessages.slice(0, userIdx + 1);
    renderMessagesFromState();
    updateActiveSessionFromMessages();
    sendMessage(null, { skipUserBubble: true });
  }

  function loadHistory() {
    var cid = getChannelId();
    coachRulesBlockEl = null;
    if (showRulesBtn) {
      showRulesBtn.classList.remove("cls3741_team_coach_btn_rules_active");
      showRulesBtn.title = "Show current rules";
    }
    loadPersonaFromStorage();

    if (!messagesEl) return;

    if (!canCoach) {
      messagesEl.innerHTML = "";
      coachingMessages = [];
      chatSessions = [];
      activeConversationId = null;
      updateCopilotLayout({ loading: false });
      renderHistoryList();
      renderRulesPanel();
      appendMessage("assistant", "Coaching is available for team admins.");
      if (inputEl) {
        inputEl.disabled = true;
        inputEl.placeholder = "Coaching is available for admins";
      }
      if (sendBtn) sendBtn.disabled = true;
      return;
    }

    if (!cid) {
      messagesEl.innerHTML = "";
      coachingMessages = [];
      chatSessions = [];
      activeConversationId = null;
      updateCopilotLayout({ loading: false });
      renderHistoryList();
      renderRulesPanel();
      appendMessage("assistant", "Select a channel first.");
      return;
    }

    if (conversationsLoading) return;
    conversationsLoading = true;
    updateCopilotLayout({ loading: true });
    messagesEl.innerHTML = '<div class="dash-copilot-empty">Loading conversations…</div>';
    coachingMessages = [];

    fetchConversationsList(cid)
      .then(function (data) {
        chatSessions = (data.conversations || []).map(mapConversationToSession);
        renderHistoryList();
        loadRulesPanel();

        var urlConvo = getConvoFromUrl();
        var reload = isPageReload();
        var targetId = null;

        if (reload) {
          if (urlConvo && chatSessions.some(function (s) { return s.id === urlConvo; })) {
            targetId = urlConvo;
          } else if (chatSessions.length) {
            targetId = chatSessions[0].id;
          }
        }

        if (targetId) {
          return activateConversation(targetId, { replaceUrl: true });
        }
        return createAndActivateNewConversation(cid);
      })
      .catch(function () {
        pendingNewChat = true;
        activeConversationId = null;
        messagesEl.innerHTML = "";
        appendMessage("assistant", "Could not load conversations.");
        renderHistoryList();
        loadRulesPanel();
      })
      .finally(function () {
        conversationsLoading = false;
        updateCopilotLayout({ loading: false });
      });
  }

  function sendMessage(presetText, opts) {
    opts = opts || {};
    if (!canCoach) {
      appendMessage("assistant", "Coaching is available for team admins.");
      return;
    }
    var cid = getChannelId();
    if (!cid) {
      appendMessage("assistant", "Please select a channel first.");
      return;
    }
    var outboundAttachment = null;
    if (!opts.skipUserBubble) {
      var text = (presetText != null ? presetText : (inputEl && inputEl.value) || "").trim();
      text = defaultTextForAttachment(pendingAttachment, text);
      outboundAttachment = buildAttachmentPayload(pendingAttachment);
      if (!text && !outboundAttachment) return;

      var attachmentForSend = pendingAttachment ? cloneAttachmentForMessage(pendingAttachment) : null;
      var userMsg = { role: "user", content: text };
      if (attachmentForSend) userMsg.attachment = attachmentForSend;
      if (outboundAttachment) userMsg._attachmentPayload = outboundAttachment;
      coachingMessages.push(userMsg);
      appendMessage("user", text, coachingMessages.length - 1, attachmentForSend);
      if (inputEl) inputEl.value = "";
      clearPendingAttachment();
      updateActiveSessionFromMessages();
    } else if (!coachingMessages.length || coachingMessages[coachingMessages.length - 1].role !== "user") {
      return;
    } else {
      var lastForRegen = coachingMessages[coachingMessages.length - 1];
      outboundAttachment = lastForRegen._attachmentPayload || null;
    }
    setLoading(true);
    var ensureConversation = activeConversationId
      ? Promise.resolve(activeConversationId)
      : createAndActivateNewConversation(cid).then(function (session) {
          return session.id;
        });

    ensureConversation.then(function (conversationId) {
      activeConversationId = conversationId;
      var requestBody = {
        channel_id: parseInt(cid, 10) || cid,
        conversation_id: conversationId,
        messages: coachingMessages.map(function (m) {
          return { role: m.role, content: m.content };
        }),
      };
      if (outboundAttachment) requestBody.attachment = outboundAttachment;
      return fetch("/discount/whatssapAPI/api/admin/coach-ai/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify(requestBody),
      });
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        setLoading(false);
        if (!data.success && data.error) {
          appendMessage("assistant", data.error || "Sorry, something went wrong. Try again.");
          updateActiveSessionFromMessages();
          return;
        }
        if (data.conversation_id) {
          activeConversationId = data.conversation_id;
          setConvoInUrl(data.conversation_id, true);
        }
        var reply = (data.message || data.reply || "").trim() || "Done. What else would you like to change?";
        var assistantMsg = {
          role: "assistant",
          content: reply,
          ui_component: data.ui_component || "none",
          component_data: data.component_data || {}
        };
        coachingMessages.push(assistantMsg);
        appendMessage(
          "assistant",
          reply,
          coachingMessages.length - 1,
          null,
          assistantMsg.ui_component,
          assistantMsg.component_data
        );
        updateActiveSessionFromMessages();
        refreshConversationsList(cid, activeConversationId);
        loadRulesPanel();
      })
      .catch(function () {
        setLoading(false);
        appendMessage("assistant", "Sorry, something went wrong. Try again.");
        updateActiveSessionFromMessages();
      });
  }

  function rulesSeparator() {
    return "\n\n";
  }

  function parseRulesText(rules) {
    var s = (rules || "").trim();
    if (!s) return [];
    var parts = s.split(/\n\n+/).map(function (x) {
      return x.trim();
    }).filter(Boolean);
    if (parts.length <= 1 && s.indexOf("\n") !== -1) {
      parts = s.split("\n").map(function (x) {
        return x.trim();
      }).filter(Boolean);
    }
    return parts;
  }

  function ruleIsActive(ruleText) {
    return currentRulesList.some(function (r) {
      return r === ruleText;
    });
  }

  function applyRuleListChange(cid, newList, rulesBlock) {
    saveRulesAndUpdate(cid, newList, rulesBlock);
  }

  function toggleRuleInList(ruleText, enable) {
    var newList = currentRulesList.slice();
    var idx = newList.indexOf(ruleText);
    if (enable) {
      if (idx === -1) newList.push(ruleText);
    } else if (idx !== -1) {
      newList.splice(idx, 1);
    }
    return newList;
  }

  function deleteRuleFromList(ruleText) {
    return currentRulesList.filter(function (r) {
      return r !== ruleText;
    });
  }

  function createRuleToggle(item, onChange) {
    var toggleWrap = document.createElement("label");
    toggleWrap.className = "dash-toggle";
    toggleWrap.title = item.preset ? "Enable or disable preset" : "Enable or disable rule";
    var input = document.createElement("input");
    input.type = "checkbox";
    input.checked = ruleIsActive(item.text);
    input.setAttribute("aria-label", (item.preset ? "Toggle preset: " : "Toggle rule: ") + item.label);
    var slider = document.createElement("span");
    slider.className = "dash-toggle-slider";
    toggleWrap.appendChild(input);
    toggleWrap.appendChild(slider);
    input.addEventListener("change", function () {
      onChange(input.checked);
    });
    return toggleWrap;
  }

  function createRuleDeleteButton(item, onDelete) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "dash-copilot-rule-delete";
    btn.title = item.preset ? "Remove preset from active rules" : "Delete rule";
    btn.setAttribute("aria-label", item.preset ? "Remove preset" : "Delete rule");
    btn.innerHTML = '<i class="fas fa-trash-alt" aria-hidden="true"></i>';
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      onDelete();
    });
    return btn;
  }

  function buildRulesPanelItems() {
    var items = [];
    var seen = {};
    PRESET_RULES.forEach(function (preset) {
      items.push({ label: preset.label, text: preset.text, preset: true });
      seen[preset.text] = true;
    });
    currentRulesList.forEach(function (text) {
      if (!seen[text]) {
        items.push({ label: truncate(text, 56), text: text, preset: false });
        seen[text] = true;
      }
    });
    return items;
  }

  function renderRulesPanel() {
    if (!rulesListEl) return;
    rulesListEl.innerHTML = "";
    var items = buildRulesPanelItems();
    if (!items.length) {
      rulesListEl.innerHTML = '<div class="dash-copilot-rule-empty">No rules yet. Toggle a preset or ask the copilot to add one.</div>';
      return;
    }
    items.forEach(function (item) {
      var card = document.createElement("div");
      card.className = "dash-copilot-rule-card" + (item.preset ? "" : " is-custom");
      var text = document.createElement("div");
      text.className = "dash-copilot-rule-text";
      text.textContent = item.label;
      if (!item.preset) {
        var tag = document.createElement("span");
        tag.className = "dash-copilot-rule-tag";
        tag.textContent = "AI";
        text.insertBefore(tag, text.firstChild);
      }
      var actions = document.createElement("div");
      actions.className = "dash-copilot-rule-actions";
      actions.appendChild(
        createRuleToggle(item, function (checked) {
          var cid = getChannelId();
          if (!cid) return;
          applyRuleListChange(cid, toggleRuleInList(item.text, checked), null);
        })
      );
      actions.appendChild(
        createRuleDeleteButton(item, function () {
          var cid = getChannelId();
          if (!cid) return;
          var msg = item.preset
            ? "Remove this preset from active rules?"
            : "Delete this AI rule permanently?";
          if (!confirm(msg)) return;
          applyRuleListChange(cid, deleteRuleFromList(item.text), null);
        })
      );
      card.appendChild(text);
      card.appendChild(actions);
      rulesListEl.appendChild(card);
    });
  }

  function loadRulesPanel() {
    var cid = getChannelId();
    if (!cid || !rulesListEl) {
      renderRulesPanel();
      return;
    }
    fetch("/discount/whatssapAPI/api/admin/coach-ai-rules/?channel_id=" + encodeURIComponent(cid))
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        currentRulesList = parseRulesText((data.rules || "").trim());
        renderRulesPanel();
      })
      .catch(function () {
        renderRulesPanel();
      });
  }

  function saveRulesAndUpdate(cid, newList, rulesBlock) {
    var newText = newList.join(rulesSeparator());
    fetch("/discount/whatssapAPI/api/admin/coach-ai-set-rules/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({ channel_id: parseInt(cid, 10) || cid, rules: newText }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (data.success) {
          currentRulesList = newList;
          renderRulesPanel();
          if (newList.length === 0 && rulesBlock) rulesBlock.remove();
        }
      })
      .catch(function () {});
  }

  function hideRules() {
    if (coachRulesBlockEl && messagesEl && coachRulesBlockEl.parentNode === messagesEl) {
      coachRulesBlockEl.remove();
      coachRulesBlockEl = null;
      scrollMessages();
    }
    if (showRulesBtn) {
      showRulesBtn.classList.remove("cls3741_team_coach_btn_rules_active");
      showRulesBtn.title = "Show current rules";
    }
  }

  function showRulesInline() {
    if (coachRulesBlockEl && messagesEl && coachRulesBlockEl.parentNode === messagesEl) {
      hideRules();
      return;
    }
    var cid = getChannelId();
    if (!cid) {
      appendMessage("assistant", "Select a channel first.");
      return;
    }
    fetch("/discount/whatssapAPI/api/admin/coach-ai-rules/?channel_id=" + encodeURIComponent(cid))
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        var rulesText = (data.rules || "").trim();
        currentRulesList = parseRulesText(rulesText);
        renderRulesPanel();
        if (!messagesEl) return;
        var hint = messagesEl.querySelector(".dash-copilot-empty");
        if (hint) hint.remove();

        var wrap = document.createElement("div");
        wrap.className = "ai-coaching-msg assistant cls3741_team_coach_rules_block";
        var title = document.createElement("div");
        title.className = "cls3741_team_coach_rules_title";
        var panelItems = buildRulesPanelItems().filter(function (item) {
          return !item.preset || ruleIsActive(item.text);
        });
        if (!panelItems.length && currentRulesList.length) {
          currentRulesList.forEach(function (ruleText) {
            panelItems.push({ label: truncate(ruleText, 80), text: ruleText, preset: false });
          });
        }
        title.textContent = panelItems.length
          ? "Rules — toggle to enable/disable, trash to delete:"
          : "No rules set for this channel.";
        wrap.appendChild(title);
        if (panelItems.length) {
          panelItems.forEach(function (item) {
            var row = document.createElement("div");
            row.className = "cls3741_team_coach_rule_item dash-copilot-inline-rule-item";
            var text = document.createElement("div");
            text.className = "cls3741_team_coach_rule_item_text";
            text.textContent = item.text;
            var actions = document.createElement("div");
            actions.className = "dash-copilot-rule-actions";
            actions.appendChild(
              createRuleToggle(item, function (checked) {
                applyRuleListChange(cid, toggleRuleInList(item.text, checked), wrap);
                if (!checked) row.remove();
              })
            );
            actions.appendChild(
              createRuleDeleteButton(item, function () {
                if (!confirm(item.preset ? "Remove this rule?" : "Delete this AI rule permanently?")) return;
                applyRuleListChange(cid, deleteRuleFromList(item.text), wrap);
                row.remove();
                if (!currentRulesList.length) title.textContent = "No rules set for this channel.";
              })
            );
            row.appendChild(text);
            row.appendChild(actions);
            wrap.appendChild(row);
          });
        }
        coachRulesBlockEl = wrap;
        messagesEl.appendChild(wrap);
        scrollMessages();
        if (showRulesBtn) {
          showRulesBtn.classList.add("cls3741_team_coach_btn_rules_active");
          showRulesBtn.title = "Hide rules";
        }
      })
      .catch(function () {
        appendMessage("assistant", "Could not load rules.");
      });
  }

  function showRules() {
    if (rulesListEl && window.matchMedia("(min-width: 1536px)").matches) {
      loadRulesPanel();
      if (rulesListEl.parentElement) {
        rulesListEl.parentElement.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
      return;
    }
    showRulesInline();
  }

  function clearRules() {
    var cid = getChannelId();
    if (!cid) {
      appendMessage("assistant", "Select a channel first.");
      return;
    }
    if (!confirm("Remove all rules for this channel?")) return;
    fetch("/discount/whatssapAPI/api/admin/coach-ai-clear-rules/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({ channel_id: parseInt(cid, 10) || cid }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (data.success) {
          hideRules();
          currentRulesList = [];
          renderRulesPanel();
          appendMessage("assistant", "Rules cleared for this channel.");
        } else {
          appendMessage("assistant", data.error || "Failed to clear rules.");
        }
      })
      .catch(function () {
        appendMessage("assistant", "Could not clear rules.");
      });
  }

  function applySuggestion(text) {
    if (inputEl) {
      inputEl.value = text;
      inputEl.focus();
    }
    sendMessage(text);
  }

  function toggleVoice() {
    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      appendMessage("assistant", "Voice input is not supported in this browser.");
      return;
    }
    if (!recognition) {
      recognition = new SpeechRecognition();
      recognition.lang = document.documentElement.lang || "en-US";
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      recognition.onresult = function (event) {
        var transcript = event.results[0][0].transcript;
        if (inputEl) inputEl.value = ((inputEl.value || "") + " " + transcript).trim();
      };
      recognition.onerror = function () {
        recognizing = false;
        if (voiceBtn) voiceBtn.classList.remove("is-recording");
      };
      recognition.onend = function () {
        recognizing = false;
        if (voiceBtn) voiceBtn.classList.remove("is-recording");
      };
    }
    if (recognizing) {
      recognition.stop();
      return;
    }
    recognizing = true;
    if (voiceBtn) voiceBtn.classList.add("is-recording");
    recognition.start();
  }

  function onFilePicked(ev) {
    var file = ev.target && ev.target.files && ev.target.files[0];
    if (!file) return;
    processSelectedFile(file);
    ev.target.value = "";
  }

  if (sendBtn) sendBtn.addEventListener("click", function () { sendMessage(); });
  if (inputEl) {
    inputEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  }
  if (showRulesBtn) showRulesBtn.addEventListener("click", showRules);
  if (clearRulesBtn) clearRulesBtn.addEventListener("click", clearRules);
  if (voiceBtn) voiceBtn.addEventListener("click", toggleVoice);
  if (fileBtn && fileInput) {
    fileBtn.addEventListener("click", function () { fileInput.click(); });
    fileInput.addEventListener("change", onFilePicked);
  }
  if (newChatBtn) {
    newChatBtn.addEventListener("click", startNewChat);
    function syncNewChatBtnState() {
      if (!newChatBtn) return;
      var draft = isDraftNewChat();
      newChatBtn.classList.toggle("is-draft", draft);
      newChatBtn.setAttribute("aria-pressed", draft ? "true" : "false");
    }
    window.syncCopilotNewChatBtn = syncNewChatBtnState;
  }
  if (historySearchEl) {
    historySearchEl.addEventListener("input", function () {
      historySearchQuery = historySearchEl.value || "";
      renderHistoryList();
    });
  }
  if (rulesSettingsBtn && clearRulesBtn) {
    rulesSettingsBtn.addEventListener("click", function () {
      clearRulesBtn.click();
    });
  }

  document.querySelectorAll("[data-copilot-suggest]").forEach(function (el) {
    el.addEventListener("click", function (e) {
      e.preventDefault();
      var persona = el.getAttribute("data-copilot-persona");
      if (persona) setPersona(persona);
      applySuggestion(el.getAttribute("data-copilot-suggest") || "");
    });
  });

  document.querySelectorAll(".ai-chat-prompt-chip[data-copilot-suggest], .dash-copilot-suggest-card[data-copilot-suggest]").forEach(function (el) {
    el.addEventListener("click", function (e) {
      e.preventDefault();
      var persona = el.getAttribute("data-copilot-persona");
      if (persona) setPersona(persona);
      applySuggestion(el.getAttribute("data-copilot-suggest") || "");
    });
  });

  document.querySelectorAll("[data-copilot-persona]").forEach(function (el) {
    el.addEventListener("click", function (e) {
      e.preventDefault();
      var persona = el.getAttribute("data-copilot-persona") || "";
      setPersona(persona);
    });
  });

  var helpBtn = document.getElementById("aiCopilotHelp");
  if (helpBtn) {
    helpBtn.addEventListener("click", function () {
      appendMessage(
        "assistant",
        "Use the left panel for chat history, the center to coach your AI, and the right panel to toggle persuasion rules. Strategy presets set your selling persona."
      );
    });
  }

  var coachJump = document.getElementById("btn_coach_ai");
  if (coachJump && copilotRoot) {
    coachJump.addEventListener("click", function (e) {
      e.stopPropagation();
      copilotRoot.scrollIntoView({ behavior: "smooth", block: "center" });
      if (inputEl && canCoach) inputEl.focus();
    });
  }

  function bindCopilotDropdowns() {
    if (!copilotRoot) return;
    copilotRoot.querySelectorAll(".dropdown").forEach(function (drop) {
      var btn = drop.querySelector("[data-bs-toggle='dropdown']");
      var menu = drop.querySelector(".dropdown-menu");
      if (!btn || !menu) return;
      var placeholder = document.createComment("copilot-dd");

      function placeMenu() {
        var r = btn.getBoundingClientRect();
        if (!placeholder.parentNode) {
          menu.parentNode.insertBefore(placeholder, menu);
        }
        document.body.appendChild(menu);
        menu.classList.add("show");
        menu.style.position = "fixed";
        menu.style.display = "block";
        menu.style.visibility = "hidden";
        menu.style.transform = "none";
        menu.style.margin = "0";
        menu.style.zIndex = "100000";
        menu.style.transition = "none";
        menu.style.animation = "none";
        menu.style.inset = "";
        var menuWidth = menu.offsetWidth || 240;
        var left = Math.round(r.right - menuWidth);
        if (left < 8) left = 8;
        menu.style.top = Math.round(r.bottom + 6) + "px";
        menu.style.left = left + "px";
        menu.style.right = "auto";
        menu.style.bottom = "auto";
        menu.style.visibility = "visible";
      }

      function restoreMenu() {
        if (placeholder.parentNode) {
          placeholder.parentNode.insertBefore(menu, placeholder);
          placeholder.parentNode.removeChild(placeholder);
        }
        menu.style.position = "";
        menu.style.top = "";
        menu.style.right = "";
        menu.style.left = "";
        menu.style.bottom = "";
        menu.style.inset = "";
        menu.style.transform = "";
        menu.style.margin = "";
        menu.style.zIndex = "";
        menu.style.display = "";
        menu.style.visibility = "";
        menu.style.transition = "";
        menu.style.animation = "";
      }

      btn.addEventListener("show.bs.dropdown", placeMenu);
      btn.addEventListener("shown.bs.dropdown", placeMenu);
      btn.addEventListener("hide.bs.dropdown", restoreMenu);
      window.addEventListener("resize", function () {
        if (menu.classList.contains("show") && menu.parentNode === document.body) placeMenu();
      });
    });
  }

  bindCopilotDropdowns();
  window.addEventListener("popstate", function () {
    var convo = getConvoFromUrl();
    if (convo && convo !== activeConversationId) {
      activateConversation(convo, { replaceUrl: false });
    }
  });
  window.reloadAiSalesCopilot = loadHistory;
  updateCopilotLayout();
  loadHistory();
})();
