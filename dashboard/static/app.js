const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const state = {
  history: [],
  voiceReplies: false,
  listening: false,
  recognition: null,
  sessionId: null,
  streaming: false,
  currentMission: null,
};

const $ = (id) => document.getElementById(id);

function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(window.toastTimer);
  window.toastTimer = setTimeout(() => el.classList.remove("show"), 3600);
}

async function api(path, options = {}) {
  console.debug("[FusionDeskTrace] UI request", { path, method: options.method || "GET" });
  const res = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  const data = await res.json();
  console.debug("[FusionDeskTrace] UI response", { path, ok: data.ok, status: res.status });
  return data;
}

async function streamFusionDeskChat(prompt, history, onEvent) {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ prompt, history, session_id: state.sessionId }),
  });
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/x-ndjson")) {
    return res.json();
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let message = "";
  let ok = false;
  let finalEvent = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      onEvent(event);
      if (event.type === "token") message += event.text || "";
      if (event.type === "done") {
        ok = true;
        finalEvent = event;
        message = event.message || message;
      }
      if (event.type === "error") {
        ok = false;
        finalEvent = event;
        message = event.message || "FusionDesk execution failed.";
      }
    }
  }

  return {
    ok,
    message,
    route: "fusiondesk",
    router_status: "FusionDesk",
    seat_engine_status: ok ? "Executed" : "Execution Error",
    local_model_status: "Bypassed",
    execution: finalEvent?.execution || {},
  };
}

function getSessionId() {
  const key = "fusiondesk.sessionId";
  let sessionId = localStorage.getItem(key);
  if (!sessionId) {
    sessionId = crypto.randomUUID ? crypto.randomUUID() : `browser-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    localStorage.setItem(key, sessionId);
  }
  state.sessionId = sessionId;
  return sessionId;
}

function setDot(el, online) {
  el.classList.toggle("online", online);
  el.classList.toggle("offline", !online);
}

function setRouteStatus({ router, seatEngine, localModel }) {
  if (router) $("routerStatus").textContent = router;
  if (seatEngine) $("seatEngineStatus").textContent = seatEngine;
  if (localModel) $("localModelStatus").textContent = localModel;
}

function isFusionDeskCommand(prompt) {
  const normalized = prompt.trim().toLowerCase();
  return [
    "use fusiondesk",
    "assign seats",
    "trademaster",
    "marketing campaign",
    "fusiondesk",
  ].some((phrase) => normalized.includes(phrase));
}

function fusionDeskTask(prompt) {
  return prompt.replace(/^use fusiondesk\s*[:-]?\s*/i, "").trim() || prompt.trim();
}

async function refresh() {
  const data = await api("/api/status");
  const online = data.server === "ok";
  setDot($("serverDot"), online);
  setDot($("stackDot"), online);
  $("serverLabel").textContent = online ? "Online" : "Offline";
  $("serverSub").textContent = data.serverModel || data.model;
  $("stackStatus").textContent = online ? "Online" : "Offline";
  $("modelName").textContent = data.model;
  $("claudeVersion").textContent = data.claude;
  $("lanUrl").textContent = data.lanUrl || "-";
  $("phoneTarget").textContent = data.phoneTarget;
  $("phoneUrl").textContent = data.lanUrl || "http://your-mac-ip:4899";
  $("routerStatus").textContent = `FusionDesk: ${data.fusiondeskStatus || "Ready"}`;
  $("localModelStatus").textContent = `Local Qwen: ${data.localQwenStatus || (online ? "Online but slow" : "Error")}`;
  if ($("telegramStatus")) {
    const telegram = data.telegram || {};
    $("telegramStatus").textContent = telegram.running ? "Running" : telegram.configured ? "Configured" : "Not configured";
    $("sessionStatus").textContent = data.sessionStoreReady ? "Persistent" : "Unavailable";
  }
  $("logBox").textContent = data.log || "No MLX log yet.";
  $("cacheCheck").className = data.modelCached ? "" : "no";
  $("launcherCheck").className = data.desktopLauncher ? "" : "no";
  $("phoneCheck").className = data.phoneReady ? "" : "no";
  if (data.flint) {
    setDot($("flintDot"), data.flint.installed);
    $("flintStatus").textContent = data.flint.installed ? "Installed" : "Ready to add";
    $("flintInstall").textContent = data.flint.installCommand;
  }
  await Promise.allSettled([loadTradeMaster(), loadCapabilities(), loadMissions()]);
}

function introMessage() {
  return {
    role: "assistant",
    content: "Local AI Console\nAsk FusionDesk, TradeMaster, Claude Code, or Codex from here. Refresh-safe sessions are stored by the backend.",
  };
}

function renderMessages(messages) {
  const box = $("messages");
  box.innerHTML = "";
  const clean = (messages || []).filter((message) => message.role && message.content);
  const displayMessages = clean.length ? clean : [introMessage()];
  state.history = [];
  displayMessages.forEach((message) => addMessage(message.role, message.content));
  state.history = clean.map((message) => ({ role: message.role, content: message.content }));
}

async function loadSession() {
  if (state.streaming) return;
  try {
    const sessionId = getSessionId();
    const data = await api(`/api/session?session_id=${encodeURIComponent(sessionId)}`);
    if (data.ok) {
      renderMessages(data.messages || []);
      if ($("memoryRecap")) $("memoryRecap").textContent = data.memory_recap || "No prior session memory available.";
      if ($("sessionStatus")) $("sessionStatus").textContent = "Persistent";
    }
  } catch (error) {
    console.warn("[FusionDeskTrace] session reconnect failed", error);
    if ($("sessionStatus")) $("sessionStatus").textContent = "Reconnecting";
  }
}

async function loadTradeMaster() {
  if (!$("trademasterStats")) return;
  const data = await api("/api/trademaster/status");
  if (!data.ok) return;
  $("trademasterStats").textContent = data.stats || "No stats generated yet.";
  $("trademasterLessons").textContent = data.lessons || "No lessons generated yet.";
  $("trademasterReviews").innerHTML = (data.recentReviews || []).map((review) => `
    <div class="memory-card">
      <strong>${escapeHtml(review.name)}</strong>
      <pre>${escapeHtml(review.preview || "")}</pre>
    </div>
  `).join("") || `<p class="muted">No reviews yet.</p>`;
}

async function loadCapabilities() {
  if (!$("capabilityMatrix")) return;
  const data = await api("/api/capabilities");
  if (!data.ok) {
    $("capabilityMatrix").innerHTML = `<p class="muted">${escapeHtml(data.message || "Capability matrix unavailable.")}</p>`;
    return;
  }
  $("capabilityMatrix").innerHTML = (data.capabilities || []).map((item) => `
    <div class="capability-card">
      <span>${escapeHtml(item.status)}</span>
      <strong>${escapeHtml(item.name)}</strong>
      <p>${escapeHtml(item.purpose)}</p>
      <small>${escapeHtml((item.connectors || []).join(", "))}</small>
    </div>
  `).join("");
}

async function loadMissions() {
  if (!$("missionList")) return;
  const data = await api("/api/missions");
  if (!data.ok) {
    $("missionList").innerHTML = `<p class="muted">${escapeHtml(data.message || "Missions unavailable.")}</p>`;
    return;
  }
  const missions = data.missions || [];
  $("missionList").innerHTML = missions.map((mission) => `
    <button class="mission-row" type="button" data-mission-id="${escapeHtml(mission.id)}">
      <span>${escapeHtml(mission.status || "unknown")}</span>
      <strong>${escapeHtml(mission.user_goal || mission.id)}</strong>
      <small>${escapeHtml(mission.task_count || 0)} tasks · approval ${mission.approvals_required ? "needed" : "not needed"}</small>
    </button>
  `).join("") || `<p class="muted">No saved missions yet.</p>`;
  document.querySelectorAll(".mission-row").forEach((button) => {
    button.addEventListener("click", async () => {
      const mission = await api(`/api/missions/${encodeURIComponent(button.dataset.missionId)}`);
      if (mission.ok) renderMission(mission.mission);
    });
  });
}

function renderMission(mission) {
  state.currentMission = mission;
  $("missionCurrent").innerHTML = `
    <div class="metric"><span>ID</span><strong>${escapeHtml(mission.id)}</strong></div>
    <div class="metric"><span>Status</span><strong>${escapeHtml(mission.status)}</strong></div>
    <div class="metric"><span>Approval Needed</span><strong>${mission.approvals_required ? "Yes" : "No"}</strong></div>
    <div class="metric"><span>Memory Path</span><strong>${escapeHtml(mission.memory_path || "Not saved")}</strong></div>
    <p class="muted">${escapeHtml(mission.user_goal)}</p>
  `;
  $("missionTasks").innerHTML = (mission.tasks || []).map((task) => `
    <div class="mission-task">
      <div>
        <span>${escapeHtml(task.id)}</span>
        <strong>${escapeHtml(task.title)}</strong>
        <small>${escapeHtml(task.seat)} · ${escapeHtml(task.model_key)} · ${escapeHtml(task.status)} · ${escapeHtml(task.verification_status)}</small>
      </div>
      <p>${escapeHtml(task.output || "No output yet.")}</p>
    </div>
  `).join("") || `<p class="muted">No tasks found for this mission.</p>`;
}

async function action(path, successPrefix) {
  toast("Working...");
  const data = await api(path, { method: "POST", body: "{}" });
  toast(data.message || (data.ok ? successPrefix : "Something did not work."));
  await refresh();
}

function escapeHtml(content) {
  return String(content).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

async function copyText(text, label = "Copied.") {
  try {
    await navigator.clipboard.writeText(text);
    toast(label);
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.focus();
    area.select();
    document.execCommand("copy");
    area.remove();
    toast(label);
  }
}

function speak(text) {
  if (!("speechSynthesis" in window)) {
    toast("Voice playback is not supported in this browser.");
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1;
  utterance.pitch = 1;
  utterance.onstart = () => $("voiceStatus").textContent = "Speaking response.";
  utterance.onend = () => $("voiceStatus").textContent = "Voice idle.";
  utterance.onerror = () => $("voiceStatus").textContent = "Voice playback stopped.";
  window.speechSynthesis.speak(utterance);
}

function addMessage(role, content) {
  state.history.push({ role, content });
  const row = document.createElement("div");
  row.className = `message ${role}`;
  row.dataset.content = content;
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "You" : "CL";
  const body = document.createElement("div");
  body.className = "message-body";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = escapeHtml(content).replace(/\n/g, "<br>");
  const tools = document.createElement("div");
  tools.className = "message-tools";
  const copy = document.createElement("button");
  copy.type = "button";
  copy.textContent = "Copy";
  copy.title = "Copy message";
  copy.addEventListener("click", () => copyText(row.dataset.content || "", "Message copied."));
  tools.appendChild(copy);
  if (role === "assistant") {
    const read = document.createElement("button");
    read.type = "button";
    read.textContent = "Read";
    read.title = "Read response aloud";
    read.addEventListener("click", () => speak(row.dataset.content || ""));
    tools.appendChild(read);
  }
  body.appendChild(bubble);
  body.appendChild(tools);
  row.appendChild(avatar);
  row.appendChild(body);
  $("messages").appendChild(row);
  $("messages").scrollTop = $("messages").scrollHeight;
  return row;
}

function updateMessage(row, content) {
  row.dataset.content = content;
  const bubble = row.querySelector(".bubble");
  if (bubble) bubble.innerHTML = escapeHtml(content).replace(/\n/g, "<br>");
  $("messages").scrollTop = $("messages").scrollHeight;
}

function renderSeatAssignment(data) {
  const seats = (data.seat_assignments || []).map((item) => `
    <div class="seat-card">
      <span>${escapeHtml(item.seat)}</span>
      <strong>${escapeHtml(item.model)}</strong>
      <p>${escapeHtml(item.reason)}</p>
    </div>
  `).join("");
  const warnings = (data.warnings || []).length
    ? `<div class="warning-list">${data.warnings.map((warning) => `<p>${escapeHtml(warning)}</p>`).join("")}</div>`
    : `<p class="muted">No warnings.</p>`;
  $("seatSummary").innerHTML = `
    <div class="metric"><span>Selected Skill</span><strong>${escapeHtml(data.selected_skill)}</strong></div>
    <div class="metric"><span>Mode</span><strong>${escapeHtml(data.mode)}</strong></div>
    <div class="metric"><span>Connectors</span><strong>${escapeHtml((data.connectors || []).join(", "))}</strong></div>
    <div class="metric"><span>Cost Tier</span><strong>${escapeHtml(data.estimated_cost_tier)}</strong></div>
    <div class="metric"><span>Confidence</span><strong>${escapeHtml(data.confidence)}</strong></div>
    <div class="seat-cards">${seats}</div>
    ${warnings}
  `;
}

function fusionDeskMessage(data) {
  return JSON.stringify({
    selected_skill: data.selected_skill,
    mode: data.mode,
    connectors: data.connectors,
    seat_assignments: data.seat_assignments,
    estimated_cost_tier: data.estimated_cost_tier,
    confidence: data.confidence,
    warnings: data.warnings || [],
  }, null, 2);
}

function copyFullChat() {
  const transcript = state.history
    .map((item) => `${item.role === "user" ? "You" : "FusionDesk"}: ${item.content}`)
    .join("\n\n");
  copyText(transcript || "No chat yet.", "Chat copied.");
}

function setupVoiceRecognition() {
  if (!SpeechRecognition) {
    $("micBtn").disabled = true;
    $("voiceStatus").textContent = "Voice input is not supported in this browser.";
    return;
  }
  const recognition = new SpeechRecognition();
  recognition.lang = "en-US";
  recognition.interimResults = true;
  recognition.continuous = false;
  state.recognition = recognition;

  recognition.onstart = () => {
    state.listening = true;
    $("micBtn").classList.add("listening");
    $("micBtn").textContent = "Stop";
    $("voiceStatus").textContent = "Listening...";
  };
  recognition.onresult = (event) => {
    let transcript = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      transcript += event.results[i][0].transcript;
    }
    $("prompt").value = transcript.trim();
    $("prompt").style.height = "auto";
    $("prompt").style.height = `${Math.min($("prompt").scrollHeight, 160)}px`;
    const last = event.results[event.results.length - 1];
    if (last && last.isFinal) {
      $("voiceStatus").textContent = "Command captured.";
      $("chatForm").requestSubmit();
    }
  };
  recognition.onerror = (event) => {
    state.listening = false;
    $("micBtn").classList.remove("listening");
    $("micBtn").textContent = "Mic";
    $("voiceStatus").textContent = `Voice input unavailable: ${event.error || "browser blocked it"}.`;
  };
  recognition.onend = () => {
    state.listening = false;
    $("micBtn").classList.remove("listening");
    $("micBtn").textContent = "Mic";
    if ($("voiceStatus").textContent === "Listening...") {
      $("voiceStatus").textContent = "Voice idle.";
    }
  };
}

document.querySelectorAll(".nav").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav, .view").forEach((el) => el.classList.remove("active"));
    button.classList.add("active");
    $(button.dataset.view).classList.add("active");
  });
});

$("refreshBtn").addEventListener("click", refresh);
$("startBtn").addEventListener("click", () => action("/api/model/start", "Model started."));
$("startModelBtn").addEventListener("click", () => action("/api/model/start", "Model started."));
$("stopModelBtn").addEventListener("click", () => action("/api/model/stop", "Model stopped."));
$("openClaudeBtn").addEventListener("click", () => action("/api/claude/open", "Opening Claude."));
$("phoneTestBtn").addEventListener("click", () => action("/api/phone/test", "Message sent."));
$("flintGithubBtn").addEventListener("click", () => action("/api/flint/github", "Opening Flint."));
$("copyChatBtn").addEventListener("click", copyFullChat);
$("voiceReplyBtn").addEventListener("click", () => {
  state.voiceReplies = !state.voiceReplies;
  $("voiceReplyBtn").textContent = state.voiceReplies ? "Voice Replies On" : "Voice Replies Off";
  $("voiceReplyBtn").setAttribute("aria-pressed", String(state.voiceReplies));
  toast(state.voiceReplies ? "Voice replies on." : "Voice replies off.");
});
$("stopVoiceBtn").addEventListener("click", () => {
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  $("voiceStatus").textContent = "Voice idle.";
});
$("micBtn").addEventListener("click", () => {
  if (!state.recognition) {
    toast("Voice input is not supported in this browser.");
    return;
  }
  if (state.listening) {
    state.recognition.stop();
    return;
  }
  try {
    state.recognition.start();
  } catch {
    toast("Voice input is already starting.");
  }
});

$("seatForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const task = $("seatTask").value.trim();
  if (!task) {
    toast("Add a task first.");
    return;
  }
  $("seatSummary").innerHTML = `<p class="muted">Assigning seats...</p>`;
  const data = await api("/api/fusiondesk/assign", {
    method: "POST",
    body: JSON.stringify({
      task,
      skill: $("seatSkill").value.trim(),
      mode: $("seatMode").value,
      costPreference: $("seatCost").value,
      qualityPreference: $("seatQuality").value,
    }),
  });
  if (!data.ok) {
    $("seatSummary").innerHTML = `<p class="muted">Error: ${escapeHtml(data.message || "Assignment failed.")}</p>`;
    return;
  }
  renderSeatAssignment(data);
});

$("tradeReviewForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("tradeReviewResult").textContent = "Running trade review...";
  const data = await api("/api/trademaster/review", {
    method: "POST",
    body: JSON.stringify({
      ticker: $("tradeTicker").value.trim(),
      direction: $("tradeDirection").value.trim(),
      entry: $("tradeEntry").value.trim(),
      exit: $("tradeExit").value.trim(),
      thesis: $("tradeThesis").value.trim(),
      notes: $("tradeNotes").value.trim(),
    }),
  });
  $("tradeReviewResult").textContent = data.message || (data.ok ? "Trade review complete." : "Trade review failed.");
  if (data.ok) await loadTradeMaster();
});

$("missionForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const userGoal = $("missionGoal").value.trim();
  if (!userGoal) {
    toast("Add a mission goal first.");
    return;
  }
  $("missionCurrent").innerHTML = `<p class="muted">Creating mission...</p>`;
  $("missionTasks").innerHTML = `<p class="muted">Routing mission tasks...</p>`;
  const data = await api("/api/missions", {
    method: "POST",
    body: JSON.stringify({ user_goal: userGoal }),
  });
  if (!data.ok) {
    $("missionCurrent").innerHTML = `<p class="muted">Error: ${escapeHtml(data.message || "Mission failed.")}</p>`;
    $("missionTasks").innerHTML = `<p class="muted">No mission tasks saved.</p>`;
    return;
  }
  renderMission(data.mission);
  $("missionGoal").value = "";
  await loadMissions();
});

$("prompt").addEventListener("input", (event) => {
  event.target.style.height = "auto";
  event.target.style.height = `${Math.min(event.target.scrollHeight, 160)}px`;
});

$("chatForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("prompt");
  const prompt = input.value.trim();
  if (!prompt) return;
  input.value = "";
  input.style.height = "auto";
  addMessage("user", prompt);
  const pending = "Thinking...";
  const pendingRow = addMessage("assistant", pending);
  let data;
  state.streaming = true;
  try {
    if (isFusionDeskCommand(prompt)) {
      setRouteStatus({ router: "FusionDesk", seatEngine: "Executing", localModel: "Bypassed" });
      let streamed = "";
      data = await streamFusionDeskChat(prompt, state.history.slice(0, -1), (event) => {
        if (event.type === "plan") {
          setRouteStatus({ router: "FusionDesk", seatEngine: "Executing", localModel: "Bypassed" });
          if (event.memory_recap) {
            updateMessage(pendingRow, `Context recap:\n${event.memory_recap}\n\nChecking tool state before execution...`);
          }
        }
        if (event.type === "start") {
          setRouteStatus({ router: "FusionDesk", seatEngine: `Executing ${event.model}`, localModel: "Bypassed" });
        }
        if (event.type === "token") {
          streamed += event.text || "";
          updateMessage(pendingRow, streamed || "Thinking...");
        }
        if (event.type === "fallback") {
          setRouteStatus({ router: "FusionDesk", seatEngine: "Fallback", localModel: "Bypassed" });
        }
        if (event.type === "error") {
          updateMessage(pendingRow, `Error: ${event.message || "Execution failed."}`);
        }
      });
    } else {
      setRouteStatus({ router: "Local Model", seatEngine: "Bypassed", localModel: "Running" });
      data = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({ prompt, history: state.history.slice(0, -1), session_id: state.sessionId }),
      });
    }
  } catch (error) {
    console.warn("[FusionDeskTrace] chat connection lost", error);
    data = {
      ok: false,
      message: "Connection lost while FusionDesk was answering. Refresh the page to reconnect to the backend session.",
      router_status: "Reconnecting",
      seat_engine_status: "Unknown",
      local_model_status: "Unknown",
    };
  } finally {
    state.streaming = false;
  }
  state.history.pop();
  const response = data.ok ? data.message : `Error: ${data.message}`;
  updateMessage(pendingRow, response);
  state.history.push({ role: "assistant", content: response });
  const finalRouteStatus = {
    router: data.router_status || (isFusionDeskCommand(prompt) ? "FusionDesk" : "Local Model"),
    seatEngine: data.seat_engine_status || (isFusionDeskCommand(prompt) ? "Returned" : "Bypassed"),
    localModel: data.local_model_status || (isFusionDeskCommand(prompt) ? "Bypassed" : (data.ok ? "Online" : "Unavailable")),
  };
  if (state.voiceReplies && data.ok) speak(response);
  await refresh();
  setRouteStatus(finalRouteStatus);
});

setupVoiceRecognition();
getSessionId();
loadSession();
refresh();
setInterval(refresh, 8000);
setInterval(loadSession, 12000);
