(() => {
  const root = document.querySelector("[data-agent-feedback]");
  if (!root || window.__agentFeedbackLoaded) return;
  window.__agentFeedbackLoaded = true;

  const __FB_BASE = document.getElementById("hermes-feedback-mount")?.dataset?.queueOrigin || "";

  const artifactPath = location.pathname;
  const storageKey = `agent-feedback:${artifactPath}`;
  const layer = root.querySelector("[data-af-layer]");
  const launcher = root.querySelector("[data-af-launcher]");
  const agentStatus = root.querySelector("[data-af-agent-status]");
  const hoverBox = root.querySelector("[data-af-hover]");
  const popover = root.querySelector("[data-af-popover]");
  const threadLog = root.querySelector("[data-af-thread-log]");
  const threadHint = root.querySelector("[data-af-thread-hint]");
  const popoverInput = root.querySelector("[data-af-popover-input]");
  const popoverSave = root.querySelector("[data-af-popover-save]");
  const popoverClose = root.querySelector("[data-af-popover-close]");
  const popoverConfig = root.querySelector("[data-af-popover-config]");
  const threadDelete = root.querySelector("[data-af-thread-delete]");
  const popoverTabs = Array.from(root.querySelectorAll("[data-af-tab]"));
  const popoverPanels = Array.from(root.querySelectorAll("[data-af-panel]"));
  const uiTag = root.querySelector("[data-af-ui-tag]");
  const uiSelected = root.querySelector("[data-af-ui-selected]");
  const uiColor = root.querySelector("[data-af-ui-color]");
  const uiBg = root.querySelector("[data-af-ui-bg]");
  const uiOpacity = root.querySelector("[data-af-ui-opacity]");
  const uiFont = root.querySelector("[data-af-ui-font]");
  const uiSize = root.querySelector("[data-af-ui-size]");
  const uiWeight = root.querySelector("[data-af-ui-weight]");
  const uiTextDot = root.querySelector("[data-af-ui-text-dot]");
  const uiBgDot = root.querySelector("[data-af-ui-bg-dot]");
  const drawer = root.querySelector("[data-af-drawer]");
  const toggle = root.querySelector("[data-af-toggle]");
  const count = root.querySelector("[data-af-count]");
  const clear = root.querySelector("[data-af-clear]");
  const menu = root.querySelector("[data-af-menu]");
  const input = root.querySelector("[data-af-input]");
  const save = root.querySelector("[data-af-save]");
  const list = root.querySelector("[data-af-list]");
  const status = root.querySelector("[data-af-status]");
  const context = root.querySelector("[data-af-context]");
  const toast = root.querySelector("[data-af-toast]");
  const close = root.querySelector("[data-af-close]");

  let armed = false;
  let activeId = null;
  let pendingComment = null;
  let hoverTarget = null;
  let visible = new URLSearchParams(location.search).get("agent-feedback") === "on"
    || localStorage.getItem(`${storageKey}:enabled`) === "true";
  let lastStatusText = "";
  let comments = load();

  function load() {
    try {
      const parsed = JSON.parse(localStorage.getItem(storageKey) || "[]");
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function persist() {
    localStorage.setItem(storageKey, JSON.stringify(comments));
  }

  // Tombstones: operator-deleted marker IDs persisted across page reloads so the
  // server's still-existing items (e.g. status "done") don't get resurrected by
  // pollStatus / SSE. The server is intentionally append-only for processed
  // markers (audit trail); the widget owns the "operator no longer wants to see
  // this on the page" half of the contract.
  const tombstoneKey = `${storageKey}:tombstones`;
  const tombstones = new Set(JSON.parse(localStorage.getItem(tombstoneKey) || "[]"));
  function tombstone(...ids) {
    let changed = false;
    for (const id of ids) if (id && !tombstones.has(id)) { tombstones.add(id); changed = true; }
    if (changed) localStorage.setItem(tombstoneKey, JSON.stringify([...tombstones]));
  }

  function makeId() {
    return `af-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function normalizeThread(thread) {
    if (!Array.isArray(thread.messages)) {
      thread.messages = [];
      if (thread.text && thread.text.trim()) {
        thread.messages.push({
          id: makeId(),
          role: "user",
          text: thread.text.trim(),
          status: thread.status || "draft",
          batchId: thread.batchId,
          createdAt: thread.updatedAt || thread.createdAt || new Date().toISOString()
        });
      }
    }
    thread.text = thread.messages
      .filter((message) => message.role === "user")
      .map((message) => message.text)
      .filter(Boolean)
      .at(-1) || "";
    return thread;
  }

  function activeThread() {
    if (pendingComment && activeId === pendingComment.id) return pendingComment;
    return comments.find((item) => item.id === activeId);
  }

  function commitPending(comment) {
    if (!pendingComment || pendingComment.id !== comment.id) return false;
    comments.push(comment);
    pendingComment = null;
    activeId = comment.id;
    return true;
  }

  function messageLabel(message) {
    if (message.role === "agent") return message.status ? `Agent · ${message.status}` : "Agent";
    if (message.status === "done") return "You · processed";
    return message.status ? `You · ${message.status}` : "You";
  }

  function canDeleteMessage(message) {
    return message.role === "user" && ["draft", "queued"].includes(message.status || "draft");
  }

  async function deleteMessage(threadId, messageId) {
    const thread = comments.find((item) => item.id === threadId);
    if (!thread) return;
    normalizeThread(thread);
    const message = thread.messages.find((item) => item.id === messageId);
    if (!message || !canDeleteMessage(message)) return;

    if (message.batchId && message.status === "queued") {
      try {
        const response = await fetch(`${__FB_BASE}/api/feedback/message?batch=${encodeURIComponent(message.batchId)}&message=${encodeURIComponent(message.id)}`, {
          method: "DELETE"
        });
        if (!response.ok) {
          const result = await response.json().catch(() => ({}));
          showToast(result.error === "already_processing" ? "Agent already processed it" : "Delete failed");
          return;
        }
      } catch {
        showToast("Delete failed");
        return;
      }
    }

    thread.messages = thread.messages.filter((item) => item.id !== messageId);
    thread.text = thread.messages.filter((item) => item.role === "user").map((item) => item.text).filter(Boolean).at(-1) || "";
    if (!thread.messages.length) {
      // Tombstone the marker AND every work-item id ever associated with it so
      // refresh doesn't restore the deleted thread from the server's queue.
      const batchIds = (thread.messages || []).map((m) => m.batchId).filter(Boolean);
      tombstone(thread.id, thread.markerId, ...batchIds);
      comments = comments.filter((item) => item.id !== thread.id);
      if (activeId === thread.id) {
        activeId = null;
        popover.classList.remove("af-open");
      }
      if (pendingComment?.id === thread.id) pendingComment = null;
    } else {
      thread.status = thread.messages.at(-1)?.status || "draft";
      delete thread.batchId;
    }
    persist();
    render();
    if (activeId === thread.id) renderThread(thread);
    showToast("Message deleted");
  }

  async function deleteThread(threadId) {
    const thread = pendingComment?.id === threadId ? pendingComment : comments.find((item) => item.id === threadId);
    if (!thread) return;
    normalizeThread(thread);
    for (const message of thread.messages) {
      if (message.role === "user" && message.status === "queued" && message.batchId) {
        try {
          await fetch(`${__FB_BASE}/api/feedback/message?batch=${encodeURIComponent(message.batchId)}&message=${encodeURIComponent(message.id)}`, {
            method: "DELETE"
          });
        } catch {
          // Best effort only. Processed conversations can still be removed locally.
        }
      }
    }
    const batchIds = (thread.messages || []).map((m) => m.batchId).filter(Boolean);
    tombstone(thread.id, thread.markerId, ...batchIds);
    comments = comments.filter((item) => item.id !== threadId);
    if (pendingComment?.id === threadId) pendingComment = null;
    if (activeId === threadId) activeId = null;
    persist();
    render();
    closePopover();
    showToast("Marker deleted");
  }

  async function clearAllThreads() {
    const queuedMessages = comments.flatMap((thread) => normalizeThread(thread).messages)
      .filter((message) => message.role === "user" && message.status === "queued" && message.batchId);
    await Promise.allSettled(queuedMessages.map((message) => (
      fetch(`${__FB_BASE}/api/feedback/message?batch=${encodeURIComponent(message.batchId)}&message=${encodeURIComponent(message.id)}`, {
        method: "DELETE"
      })
    )));
    // Tombstone every marker + every batch id we knew about so refresh / SSE
    // don't resurrect them from the server's audit trail.
    const ids = [];
    for (const thread of comments) {
      ids.push(thread.id, thread.markerId);
      for (const m of thread.messages || []) ids.push(m.batchId);
    }
    tombstone(...ids);
    comments = [];
    pendingComment = null;
    activeId = null;
    persist();
    closePopover();
    render();
    showToast("All markers cleared");
  }

  function renderThread(thread) {
    normalizeThread(thread);
    threadLog.innerHTML = "";
    if (!thread.messages.length) {
      const empty = document.createElement("div");
      empty.className = "af-thread-empty";
      empty.textContent = "Start a focused chat about this item.";
      threadLog.append(empty);
    }
    thread.messages.forEach((message) => {
      const bubble = document.createElement("div");
      bubble.className = `af-msg af-msg-${message.role === "agent" ? "agent" : "user"} ${message.status === "done" ? "af-msg-done" : ""}`;
      bubble.innerHTML = "<span class=\"af-msg-meta\"></span><div class=\"af-msg-text\"></div>";
      bubble.querySelector(".af-msg-meta").textContent = messageLabel(message);
      bubble.querySelector(".af-msg-text").textContent = message.text || "";
      if (canDeleteMessage(message)) {
        const del = document.createElement("button");
        del.type = "button";
        del.className = "af-msg-delete";
        del.setAttribute("aria-label", "Delete queued message");
        del.textContent = "×";
        del.addEventListener("click", (event) => {
          event.stopPropagation();
          deleteMessage(thread.id, message.id);
        });
        bubble.append(del);
      }
      threadLog.append(bubble);
    });
    threadLog.scrollTop = threadLog.scrollHeight;
    threadHint.textContent = "Chat stays attached to this marker.";
    threadDelete.classList.toggle("af-show", thread.messages.length > 0 && !pendingComment);
  }

  async function sendThreads(threads) {
    const ready = threads
      .map((thread) => normalizeThread(thread))
      .map((thread) => ({
        thread,
        unsent: thread.messages.filter((message) => message.role === "user" && message.text.trim() && !message.batchId)
      }))
      .filter((entry) => entry.unsent.length);

    if (!ready.length) {
      showToast("Add a message first");
      return null;
    }

    const payload = {
      artifactPath,
      artifactTitle: document.title,
      artifactVersion: document.querySelector("meta[name='agent-feedback-version']")?.content || "unversioned",
      sentAt: new Date().toISOString(),
      comments: ready.map(({ thread, unsent }) => ({
        ...thread,
        text: unsent.map((message) => message.text).join("\n\n"),
        messages: unsent
      }))
    };

    try {
      const response = await fetch(`${__FB_BASE}/api/feedback`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      ready.forEach(({ thread, unsent }) => {
        const workItem = (result.items || []).find((item) => item.markerId === thread.id || item.marker?.id === thread.id) || result;
        thread.status = "queued";
        unsent.forEach((message) => {
          message.status = "queued";
          message.batchId = workItem.id;
        });
      });
      persist();
      render();
      if (activeId) {
        const active = activeThread();
        if (active) renderThread(active);
      }
      showToast("Sent to agent");
      return result;
    } catch {
      showToast("Send failed");
      return null;
    }
  }

  function cssPath(el) {
    if (!el || !el.tagName || el === document.body) return "body";
    if (el.id) return `#${CSS.escape(el.id)}`;
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.body && parts.length < 5) {
      let part = node.tagName.toLowerCase();
      if (node.classList.length) part += `.${Array.from(node.classList).slice(0, 2).map(CSS.escape).join(".")}`;
      const parent = node.parentElement;
      if (parent) {
        const same = Array.from(parent.children).filter((child) => child.tagName === node.tagName);
        if (same.length > 1) part += `:nth-of-type(${same.indexOf(node) + 1})`;
      }
      parts.unshift(part);
      node = parent;
    }
    return parts.join(" > ") || "body";
  }

  function uiSnapshot(el) {
    const style = window.getComputedStyle(el);
    return {
      tag: el.tagName.toLowerCase(),
      color: style.color,
      backgroundColor: style.backgroundColor,
      opacity: style.opacity,
      fontFamily: style.fontFamily,
      fontSize: style.fontSize,
      fontWeight: style.fontWeight
    };
  }

  function setTab(name) {
    popoverTabs.forEach((tab) => {
      tab.setAttribute("aria-selected", String(tab.dataset.afTab === name));
    });
    popoverPanels.forEach((panel) => {
      panel.classList.toggle("af-active", panel.dataset.afPanel === name);
    });
  }

  function expandPopover(tab = "agent") {
    popover.classList.add("af-expanded");
    popoverConfig.setAttribute("aria-expanded", "true");
    setTab(tab);
    refreshThreadDelete();
  }

  function collapsePopover() {
    popover.classList.remove("af-expanded");
    popoverConfig.setAttribute("aria-expanded", "false");
  }

  function renderUiPanel(comment) {
    const meta = comment.ui || {};
    uiTag.textContent = meta.tag || comment.selector?.split(" > ").at(-1)?.replace(/:nth-of-type\(\d+\)/g, "") || "element";
    uiSelected.textContent = comment.selector || "Selected item unavailable.";
    uiColor.textContent = meta.color || "rgb(20, 20, 19)";
    uiBg.textContent = meta.backgroundColor || "rgb(255, 255, 255)";
    uiOpacity.textContent = meta.opacity || "1";
    uiFont.textContent = meta.fontFamily || "system-ui";
    uiSize.textContent = meta.fontSize || "14px";
    uiWeight.textContent = meta.fontWeight || "400";
    uiTextDot.style.setProperty("--af-dot", meta.color || "#141413");
    uiBgDot.style.setProperty("--af-dot", meta.backgroundColor || "#fff");
  }

  function selectedText() {
    const text = String(window.getSelection ? window.getSelection() : "").trim();
    return text.length > 240 ? `${text.slice(0, 240)}...` : text;
  }

  function elementAtPoint(clientX, clientY) {
    const feedbackNodes = [
      layer,
      hoverBox,
      popover,
      drawer,
      root.querySelector("[data-af-toolbar]"),
      launcher,
      agentStatus
    ].filter(Boolean);
    const previous = feedbackNodes.map((node) => [node, node.style.pointerEvents]);
    feedbackNodes.forEach((node) => { node.style.pointerEvents = "none"; });
    const candidates = document.elementsFromPoint(clientX, clientY)
      .filter((candidate) => !candidate.closest("[data-agent-feedback]"))
      .filter((candidate) => !["HTML", "BODY"].includes(candidate.tagName))
      .filter((candidate) => {
        const rect = candidate.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      })
      .sort((a, b) => {
        const ar = a.getBoundingClientRect();
        const br = b.getBoundingClientRect();
        return (ar.width * ar.height) - (br.width * br.height);
      });
    previous.forEach(([node, value]) => { node.style.pointerEvents = value; });
    return candidates[0] || document.elementFromPoint(clientX, clientY);
  }

  function rectForElement(element) {
    const rect = element.getBoundingClientRect();
    return {
      x: rect.left + window.scrollX,
      y: rect.top + window.scrollY,
      width: rect.width,
      height: rect.height
    };
  }

  function placeBox(box, rect) {
    box.style.left = `${rect.x}px`;
    box.style.top = `${rect.y}px`;
    box.style.width = `${Math.max(rect.width, 8)}px`;
    box.style.height = `${Math.max(rect.height, 8)}px`;
  }

  function placePopover(comment) {
    const rect = comment.rect || {
      x: comment.pageX,
      y: comment.pageY,
      width: 1,
      height: 1
    };
    const margin = 10;
    const width = Math.min(360, window.innerWidth - 28);
    let left = rect.x + rect.width + margin;
    if (left + width > window.scrollX + window.innerWidth - margin) {
      left = Math.max(window.scrollX + margin, rect.x - width - margin);
    }
    let top = rect.y + Math.min(rect.height, 46);
    top = Math.max(window.scrollY + margin, Math.min(top, window.scrollY + window.innerHeight - 220));
    popover.style.left = `${left}px`;
    popover.style.top = `${top}px`;
  }

  function render() {
    comments.forEach(normalizeThread);
    comments = comments.filter((comment) => comment.messages.length > 0);
    layer.style.width = `${Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)}px`;
    layer.style.height = `${Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)}px`;
    layer.querySelectorAll(".af-marker, .af-select-box").forEach((marker) => marker.remove());
    if (visible) {
      comments.forEach((comment, index) => {
        if (comment.rect) {
          const selectBox = document.createElement("div");
          selectBox.className = "af-select-box";
          placeBox(selectBox, comment.rect);
          layer.append(selectBox);
        }
        const marker = document.createElement("button");
        marker.type = "button";
        marker.className = "af-marker";
        marker.dataset.afMarker = "";
        marker.textContent = String(index + 1);
        marker.style.left = `${comment.markerX || comment.pageX}px`;
        marker.style.top = `${comment.markerY || comment.pageY}px`;
        marker.addEventListener("click", (event) => {
          event.stopPropagation();
          openComment(comment.id);
        });
        layer.append(marker);
      });
    }

    count.textContent = String(comments.length);
    root.querySelector("[data-af-toolbar]")?.classList.toggle("af-hidden", !visible);
    launcher.setAttribute("aria-pressed", String(visible));
    list.innerHTML = comments.length ? "" : "<div class=\"af-card\"><p>No comments yet.</p></div>";
    comments.forEach((comment, index) => {
      const card = document.createElement("article");
      card.className = "af-card";
      card.innerHTML = `
        <div class="af-card-head"><span>Comment ${index + 1}</span><span>${comment.status || "draft"}</span></div>
        <p></p>
        <small></small>
      `;
      const messageCount = normalizeThread(comment).messages.length;
      card.querySelector(".af-card-head span:first-child").textContent = `Marker ${index + 1}`;
      card.querySelector("p").textContent = comment.text || `${messageCount} message(s)`;
      card.querySelector("small").textContent = comment.selector || `${Math.round(comment.viewportX)}, ${Math.round(comment.viewportY)}`;
      card.addEventListener("click", () => openComment(comment.id));
      list.append(card);
    });
  }

  function openComment(id) {
    activeId = id;
    const comment = activeThread();
    if (!comment) return;
    normalizeThread(comment);
    popoverInput.value = "";
    renderThread(comment);
    renderUiPanel(comment);
    placePopover(comment);
    popover.classList.add("af-open");
    collapsePopover();
    popoverInput.focus();
  }

  function closePopover() {
    if (pendingComment && activeId === pendingComment.id) {
      pendingComment = null;
      activeId = null;
    }
    popover.classList.remove("af-open");
    collapsePopover();
  }

  function refreshThreadDelete() {
    const thread = activeThread();
    threadDelete.classList.toggle("af-show", !!thread && normalizeThread(thread).messages.length > 0 && !pendingComment);
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("af-show");
    window.setTimeout(() => toast.classList.remove("af-show"), 1800);
  }

  function openInbox() {
    if (activeId) {
      openComment(activeId);
      return;
    }
    const lastThread = comments.at(-1);
    if (lastThread) {
      openComment(lastThread.id);
      return;
    }
    showToast("Select an item first");
  }

  function setAgentStatus(item) {
    if (!item) {
      agentStatus.classList.remove("af-show");
      return;
    }
    const message = item.agentMessage || `${item.payload?.comments?.length || 0} comment(s) ${item.status}`;
    const text = `Agent feedback ${item.status}: ${message}`;
    agentStatus.innerHTML = `<strong>Agent · ${item.status}</strong><span></span>`;
    agentStatus.querySelector("span").textContent = message;
    agentStatus.classList.add("af-show");
    if (lastStatusText && lastStatusText !== text) showToast(text);
    lastStatusText = text;
  }

  function setArmed(next) {
    armed = next;
    toggle.setAttribute("aria-pressed", String(armed));
    layer.classList.toggle("af-armed", armed);
    layer.setAttribute("aria-hidden", String(!armed));
    if (!armed) {
      hoverBox.style.display = "none";
      hoverTarget = null;
    }
  }

  toggle.addEventListener("click", () => setArmed(!armed));
  count.addEventListener("click", openInbox);
  agentStatus.addEventListener("click", openInbox);
  launcher.addEventListener("click", () => {
    visible = !visible;
    if (visible) {
      localStorage.setItem(`${storageKey}:enabled`, "true");
      drawer.classList.remove("af-minimized");
    } else {
      localStorage.removeItem(`${storageKey}:enabled`);
      setArmed(false);
      drawer.classList.add("af-minimized");
      closePopover();
    }
    render();
  });
  menu.addEventListener("click", openInbox);
  close.addEventListener("click", () => drawer.classList.remove("af-open"));
  popoverClose.addEventListener("click", closePopover);
  popoverConfig.addEventListener("click", () => {
    if (popover.classList.contains("af-expanded")) {
      collapsePopover();
      return;
    }
    expandPopover("agent");
  });
  popoverTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      expandPopover(tab.dataset.afTab);
    });
  });
  threadDelete.addEventListener("click", () => {
    if (activeId) deleteThread(activeId);
  });
  popoverInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      popoverSave.click();
    }
  });

  layer.addEventListener("mousemove", (event) => {
    if (!armed) return;
    const element = elementAtPoint(event.clientX, event.clientY);
    if (!element || element === hoverTarget) return;
    hoverTarget = element;
    const rect = rectForElement(element);
    placeBox(hoverBox, rect);
    hoverBox.style.display = "block";
  });

  layer.addEventListener("click", (event) => {
    if (!armed || event.target.classList.contains("af-marker")) return;
    const element = elementAtPoint(event.clientX, event.clientY);
    if (!element) return;
    const rect = rectForElement(element);
    const comment = {
      id: makeId(),
      text: "",
      status: "draft",
      messages: [],
      pageX: event.pageX,
      pageY: event.pageY,
      markerX: rect.x + rect.width,
      markerY: rect.y + Math.min(rect.height, 88),
      viewportX: event.clientX,
      viewportY: event.clientY,
      rect,
      selector: cssPath(element),
      ui: uiSnapshot(element),
      selectedText: selectedText(),
      url: location.href,
      title: document.title,
      viewport: { width: window.innerWidth, height: window.innerHeight },
      createdAt: new Date().toISOString()
    };
    pendingComment = comment;
    activeId = comment.id;
    render();
    openComment(comment.id);
  });

  save.addEventListener("click", () => {
    const comment = comments.find((item) => item.id === activeId);
    if (!comment) return;
    comment.text = input.value.trim();
    comment.updatedAt = new Date().toISOString();
    persist();
    render();
    showToast("Comment saved");
  });

  popoverSave.addEventListener("click", async () => {
    const comment = activeThread();
    if (!comment) return;
    const text = popoverInput.value.trim();
    if (!text) {
      showToast("Write a message first");
      return;
    }
    normalizeThread(comment).messages.push({
      id: makeId(),
      role: "user",
      text,
      status: "draft",
      createdAt: new Date().toISOString()
    });
    comment.text = text;
    comment.updatedAt = new Date().toISOString();
    commitPending(comment);
    persist();
    render();
    popoverInput.value = "";
    renderThread(comment);
    const sent = await sendThreads([comment]);
    if (sent) {
      closePopover();
      setArmed(false);
    }
  });

  clear.addEventListener("click", clearAllThreads);

  function ensureThreadFromServerItem(item) {
    const marker = item?.marker || item?.payload?.comments?.[0];
    const markerId = item?.markerId || marker?.markerId || marker?.id;
    if (!marker || !markerId) return null;
    // Don't resurrect threads the operator deleted. Two cases:
    //   (a) Server flipped item.status to "canceled" (all messages removed
    //       on the server side — happens for queued-message deletions).
    //   (b) Operator deleted a done/processed thread locally — server still
    //       has it (intentional audit trail), but the tombstone list says
    //       "this marker is no longer wanted on the page".
    if (item.status === "canceled") return null;
    if (tombstones.has(item.id) || tombstones.has(markerId)) return null;
    let thread = comments.find((entry) => {
      normalizeThread(entry);
      return entry.id === markerId
        || entry.markerId === markerId
        || entry.messages.some((message) => message.batchId === item.id);
    });
    if (thread) return thread;

    thread = {
      ...marker,
      id: markerId,
      markerId,
      text: marker.text || item.latestUserMessage || item.visibleText || "",
      status: item.status || marker.status || "queued",
      messages: Array.isArray(marker.messages) ? marker.messages.map((message) => ({
        ...message,
        status: message.status === "draft" ? (item.status || "queued") : (message.status || item.status || "queued"),
        batchId: message.batchId || item.id
      })) : []
    };
    normalizeThread(thread);
    comments.push(thread);
    return thread;
  }

  async function pollStatus() {
    try {
      const response = await fetch(`${__FB_BASE}/api/feedback/status?artifact=${encodeURIComponent(artifactPath)}`);
      if (!response.ok) return;
      const result = await response.json();
      if (result.latest) {
        const message = result.latest.agentMessage ? ` — ${result.latest.agentMessage}` : "";
        status.textContent = `Latest batch ${result.latest.id}: ${result.latest.status}${message}`;
        for (const item of result.items || [result.latest]) {
          ensureThreadFromServerItem(item);
          if (!item || !["done", "canceled"].includes(item.status)) continue;
          comments.forEach((thread) => {
            normalizeThread(thread);
            const relatedMessages = thread.messages.filter((message) => message.batchId === item.id);
            if (!relatedMessages.length) return;
            relatedMessages.forEach((message) => {
              message.status = item.status === "done" ? "done" : "canceled";
            });
            if (item.agentMessage && !thread.messages.some((message) => message.role === "agent" && message.batchId === item.id)) {
              thread.messages.push({
                id: makeId(),
                role: "agent",
                text: item.agentMessage,
                status: item.status,
                batchId: item.id,
                createdAt: item.updatedAt || new Date().toISOString()
              });
            }
            thread.status = item.status;
          });
        }
        if (result.latest.agentMessage) {
          comments.forEach((thread) => {
            normalizeThread(thread);
            const hasBatch = thread.batchId === result.latest.id
              || thread.messages.some((item) => item.batchId === result.latest.id);
            const alreadyAdded = thread.messages.some((item) => item.role === "agent" && item.batchId === result.latest.id);
            if (hasBatch && !alreadyAdded) {
              thread.messages.push({
                id: makeId(),
                role: "agent",
                text: result.latest.agentMessage,
                status: result.latest.status,
                batchId: result.latest.id,
                createdAt: result.latest.updatedAt || new Date().toISOString()
              });
              thread.status = result.latest.status;
            }
          });
          persist();
          render();
          const active = comments.find((item) => item.id === activeId);
          if (active) renderThread(active);
        } else {
          persist();
          render();
        }
        setAgentStatus(result.latest);
      }
    } catch {
      return;
    }
  }

  render();
  pollStatus();
  window.addEventListener("resize", render);
  window.addEventListener("keydown", (event) => {
    if (event.altKey && event.shiftKey && event.key.toLowerCase() === "a") {
      visible = true;
      localStorage.setItem(`${storageKey}:enabled`, "true");
      drawer.classList.remove("af-minimized");
      render();
      showToast("Agent feedback controls shown");
    }
  });

  // ---- Auto-reload trigger ----
  // Declared BEFORE the SSE/setInterval bindings so they capture the wrapped
  // function. Earlier ordering had setInterval(pollStatus,…) capture the
  // ORIGINAL by reference, which bypassed the reload check on safety-net polls.
  const reloadedKey = `${storageKey}:reloaded`;
  const alreadyReloaded = new Set(JSON.parse(localStorage.getItem(reloadedKey) || "[]"));
  const origPollStatus = pollStatus;
  pollStatus = async function pollStatusWrapped() {
    await origPollStatus.apply(this, arguments);
    try {
      const r = await fetch(`${__FB_BASE}/api/feedback/status?artifact=${encodeURIComponent(artifactPath)}`);
      if (!r.ok) return;
      const result = await r.json();
      // Collect every pending reload first, then add ALL to the seen-set BEFORE
      // scheduling, so a race that fires multiple pollStatus calls in quick
      // succession doesn't schedule N reloads (only the first item triggers,
      // the rest are pre-marked as handled).
      const pending = (result.items || []).filter(
        (item) => item.reload && item.status === "done" && !alreadyReloaded.has(item.id)
      );
      if (!pending.length) return;
      for (const item of pending) alreadyReloaded.add(item.id);
      localStorage.setItem(reloadedKey, JSON.stringify([...alreadyReloaded]));
      // Reload mode escalates to "full" if ANY pending item demands it; otherwise
      // default to "css" hot-swap (the dominant case — preserves runtime state).
      const wantsFull = pending.some((item) => item.reloadMode === "full");
      if (wantsFull) {
        showToast(`Agent applied a change — reloading page…`);
        setTimeout(() => {
          const u = new URL(location.href);
          u.searchParams.set("_fb_reload", Date.now().toString());
          location.replace(u.toString());
        }, 600);
      } else {
        showToast(`Agent applied a change — refreshing styles…`);
        // CSS hot-swap: replace each <link rel="stylesheet"> with a cloned link
        // that carries a cache-bust query param. Browser fetches fresh (different
        // URL = cache miss), applies new rules, removes old node. No page reload,
        // no runtime state loss, instant visible change for CSS edits.
        setTimeout(() => {
          const cb = Date.now().toString();
          document.querySelectorAll('link[rel="stylesheet"]').forEach((link) => {
            if (!link.href) return;
            const fresh = link.cloneNode();
            const u = new URL(link.href, location.origin);
            u.searchParams.set("_fb_cb", cb);
            fresh.href = u.toString();
            link.parentNode.insertBefore(fresh, link.nextSibling);
            fresh.addEventListener("load", () => { link.remove(); }, { once: true });
            fresh.addEventListener("error", () => { fresh.remove(); }, { once: true });
          });
        }, 400);
      }
    } catch {}
  };

  // Push channel: SSE. Replaces 5s polling. pollStatus is now the wrapped
  // version, so both SSE-triggered calls and the safety-net interval get the
  // reload check. EventSource auto-reconnects on disconnect.
  const sseUrl = `${__FB_BASE}/api/feedback/events?artifact=${encodeURIComponent(artifactPath)}`;
  let sse = null;
  try {
    sse = new EventSource(sseUrl);
    sse.addEventListener("message", () => { pollStatus(); });
    sse.addEventListener("error", () => { /* auto-reconnects */ });
  } catch (e) {
    window.setInterval(() => pollStatus(), 2000);
  }
  // Safety net via arrow-function so the *current* (wrapped) pollStatus is
  // resolved at every tick — never the original.
  window.setInterval(() => pollStatus(), 30_000);
})();
