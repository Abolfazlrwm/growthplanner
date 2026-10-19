(() => {
  "use strict";

  const root = document.querySelector("[data-assistant]");
  if (!root) return;

  const form = root.querySelector("[data-assistant-form]");
  const chat = root.querySelector("#assistant-chat");
  const message = root.querySelector("[data-assistant-message]");
  const mode = root.querySelector("[data-assistant-mode]");
  const consent = root.querySelector("[data-assistant-consent]");
  const submit = root.querySelector("[data-assistant-submit]");
  const submitLabel = root.querySelector("[data-submit-label]");
  const spinner = root.querySelector(".assistant-spinner");
  const status = root.querySelector("[data-assistant-status]");
  const clear = root.querySelector("[data-assistant-clear]");
  const lang = root.dataset.lang === "en" ? "en" : "fa";
  let lastPayload = null;

  const copy = lang === "en" ? {
    you: "You", planner: "Planner", thinking: "Thinking through your plan…", retry: "Retry last message",
    accepted: "Added to your tasks.", confirm: "Add to tasks", adding: "Adding…", cleared: "History cleared.",
    generic: "Something went wrong. Please try again.", network: "Could not reach the assistant. Please try again.",
    when: "When", priority: "Priority", goal: "Goal",
  } : {
    you: "شما", planner: "برنامه‌یار", thinking: "دارم درباره‌ی برنامه‌ات فکر می‌کنم…", retry: "تلاش دوباره برای همین پیام",
    accepted: "به تسک‌ها اضافه شد.", confirm: "افزودن به تسک‌ها", adding: "در حال افزودن…", cleared: "گفت‌وگو پاک شد.",
    generic: "مشکلی پیش آمد. دوباره امتحان کن.", network: "ارتباط با دستیار برقرار نشد. دوباره امتحان کن.",
    when: "زمان", priority: "اولویت", goal: "هدف",
  };

  function csrfToken() {
    const input = form.querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function setStatus(text = "", kind = "") {
    status.textContent = text;
    status.className = `assistant-status${kind ? ` is-${kind}` : ""}`;
  }

  function setPending(pending) {
    submit.disabled = pending;
    message.disabled = pending;
    mode.disabled = pending;
    consent.disabled = pending;
    spinner.hidden = !pending;
    if (!pending) submitLabel.textContent = lang === "en" ? "Ask" : "بپرس";
  }

  function scrollDown() {
    requestAnimationFrame(() => chat.scrollIntoView({ block: "end", behavior: "smooth" }));
  }

  function addBubble(role, text) {
    const welcome = chat.querySelector("[data-assistant-welcome]");
    if (welcome) welcome.remove();
    const article = document.createElement("article");
    article.className = `assistant-bubble assistant-bubble--${role}`;
    const label = document.createElement("span");
    label.className = "assistant-bubble-label";
    label.textContent = role === "user" ? copy.you : copy.planner;
    const paragraph = document.createElement("p");
    // textContent keeps provider/user text inert; no Markdown/HTML execution is allowed.
    paragraph.textContent = text;
    article.append(label, paragraph);
    chat.append(article);
    scrollDown();
  }

  function priorityText(priority) {
    const fa = { high: "زیاد", medium: "متوسط", low: "کم" };
    return lang === "en" ? priority : (fa[priority] || priority);
  }

  function addDrafts(suggestions) {
    if (!Array.isArray(suggestions) || !suggestions.length) return;
    const list = document.createElement("section");
    list.className = "assistant-drafts";
    suggestions.forEach((suggestion) => {
      const card = document.createElement("article");
      card.className = "assistant-draft";
      const title = document.createElement("h3");
      title.textContent = suggestion.title;
      const detail = document.createElement("p");
      const bits = [`${copy.when}: ${suggestion.date}`, `${copy.priority}: ${priorityText(suggestion.priority)}`];
      if (suggestion.start_time) bits.push(`${suggestion.start_time}${suggestion.end_time ? `–${suggestion.end_time}` : ""}`);
      if (suggestion.goal_id) bits.push(`${copy.goal}: #${suggestion.goal_id}`);
      detail.textContent = bits.join(" · ");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = copy.confirm;
      button.addEventListener("click", () => acceptDraft(suggestion.draft_id, button));
      card.append(title, detail, button);
      list.append(card);
    });
    chat.append(list);
    scrollDown();
  }

  async function api(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(), "Accept": "application/json" },
      body: JSON.stringify(payload),
    });
    let data = {};
    try { data = await response.json(); } catch (_) { /* Deliberately use a safe generic error. */ }
    if (!response.ok) {
      const error = new Error(data.error || copy.generic);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  async function send(payload) {
    setPending(true);
    setStatus(copy.thinking, "pending");
    try {
      const data = await api(root.dataset.chatUrl, payload);
      root.dataset.conversationId = data.conversation_id || root.dataset.conversationId;
      if (clear) clear.disabled = false;
      addBubble("assistant", data.answer);
      addDrafts(data.suggestions);
      setStatus("");
      lastPayload = null;
    } catch (error) {
      setStatus(`${error.message || copy.network} ${copy.retry}`, "error");
      lastPayload = payload;
    } finally {
      setPending(false);
      message.focus();
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = message.value.trim();
    if (!text) {
      setStatus(lang === "en" ? "Write a message first." : "اول یک پیام بنویس.", "error");
      message.focus();
      return;
    }
    const payload = {
      message: text,
      mode: mode.value,
      share_metadata: consent.checked,
      conversation_id: root.dataset.conversationId || null,
    };
    addBubble("user", text);
    message.value = "";
    send(payload);
  });

  status.addEventListener("click", () => {
    if (!lastPayload || submit.disabled) return;
    addBubble("user", lastPayload.message);
    send(lastPayload);
  });
  status.addEventListener("keydown", (event) => {
    if ((event.key === "Enter" || event.key === " ") && lastPayload) {
      event.preventDefault();
      status.click();
    }
  });

  async function acceptDraft(draftId, button) {
    button.disabled = true;
    button.textContent = copy.adding;
    try {
      const data = await api(root.dataset.acceptUrl, { draft_id: draftId });
      button.textContent = data.already_accepted ? copy.accepted : copy.accepted;
      setStatus(copy.accepted, "success");
    } catch (error) {
      button.disabled = false;
      button.textContent = copy.confirm;
      setStatus(error.message || copy.generic, "error");
    }
  }

  if (clear) {
    clear.addEventListener("click", async () => {
      if (clear.disabled) return;
      clear.disabled = true;
      try {
        await api(root.dataset.clearUrl, { conversation_id: root.dataset.conversationId || null });
        root.dataset.conversationId = "";
        chat.replaceChildren();
        const welcome = document.createElement("div");
        welcome.className = "assistant-welcome";
        const star = document.createElement("span"); star.textContent = "✦";
        const question = document.createElement("p");
        question.textContent = lang === "en" ? "What would make this week feel more manageable?" : "چه چیزی این هفته را برایت قابل‌مدیریت‌تر می‌کند؟";
        welcome.append(star, question);
        chat.append(welcome);
        setStatus(copy.cleared, "success");
      } catch (error) {
        setStatus(error.message || copy.generic, "error");
      } finally {
        clear.disabled = !root.dataset.conversationId;
      }
    });
  }
})();
