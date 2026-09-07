"use strict";

import robotArt1 from "./dashboard-robot-art-1.js?v=png-face-2";
import robotArt2 from "./dashboard-robot-art-2.js?v=png-face-2";
import robotArt3 from "./dashboard-robot-art-3.js?v=png-face-2";
import robotArt4 from "./dashboard-robot-art-4.js?v=png-face-2";

// Robot del dashboard: usa la ilustración exacta compartida por Danilo como
// base visual y anima únicamente la expresión sobre el visor.
const STYLE_ID = "dashboard-robot-face-style";
const ROBOT_ART_URL = `data:image/webp;base64,${robotArt1}${robotArt2}${robotArt3}${robotArt4}`;
let activeRobot = null;

const MOUTH_SHAPES = {
  idle: "M 45 28 Q 80 55 115 28",
  working: "M 50 36 Q 80 32 110 36",
  success: "M 38 24 Q 80 60 122 24",
  error: "M 45 48 Q 80 18 115 48",
  sleep: "M 52 36 Q 80 42 108 36",
  talkA: "M 58 32 Q 80 48 102 32 Q 80 18 58 32",
  talkB: "M 52 31 Q 80 56 108 31",
};

function installStylesheet() {
  if (document.getElementById(STYLE_ID)) return;
  const link = document.createElement("link");
  link.id = STYLE_ID;
  link.rel = "stylesheet";
  link.href = new URL("./dashboard-robot.css?v=png-face-2", import.meta.url).href;
  document.head.appendChild(link);
}

function statusToState(value) {
  const status = String(value || "").trim().toUpperCase();
  if (status === "RUNNING") return "working";
  if (status === "PASS" || status === "SUCCESS") return "success";
  if (status === "FAIL" || status === "ERROR") return "error";
  if (status === "WARNING") return "working";
  return "idle";
}

function buildFace(robot) {
  robot.classList.add("utel-robot-face", "utel-robot-png-face");
  robot.dataset.state = "idle";
  robot.replaceChildren();
  robot.insertAdjacentHTML("afterbegin", `
    <img class="utel-robot-art" src="${ROBOT_ART_URL}" alt="" draggable="false" aria-hidden="true" />
    <span class="utel-robot-face-overlay" aria-hidden="true">
      <span class="utel-robot-eyes">
        <span class="utel-robot-eye eye-left"><span class="utel-robot-pupil"></span></span>
        <span class="utel-robot-eye eye-right"><span class="utel-robot-pupil"></span></span>
      </span>
      <svg class="utel-robot-mouth" viewBox="0 0 160 70" aria-hidden="true">
        <path d="${MOUTH_SHAPES.idle}" fill="none" stroke="currentColor" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"></path>
      </svg>
    </span>
  `);
}

function createRobotController(robot) {
  const stage = robot.closest(".latest-panel") || robot.closest(".execution-radar") || robot.parentElement;
  const eyes = robot.querySelector(".utel-robot-eyes");
  const mouth = robot.querySelector(".utel-robot-mouth path");
  const status = document.querySelector("#latest-status");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  let state = "idle";
  let blinkTimer = 0;
  let talkingTimer = 0;
  let isBlinking = false;
  let destroyed = false;

  const setMouth = (shape) => mouth?.setAttribute("d", shape);
  const stopTalking = () => {
    window.clearInterval(talkingTimer);
    talkingTimer = 0;
  };

  function startTalking() {
    stopTalking();
    if (reducedMotion.matches) {
      setMouth(MOUTH_SHAPES.working);
      return;
    }
    let flip = false;
    talkingTimer = window.setInterval(() => {
      flip = !flip;
      setMouth(flip ? MOUTH_SHAPES.talkA : MOUTH_SHAPES.talkB);
    }, 180);
  }

  function applyState(nextState) {
    if (destroyed || !MOUTH_SHAPES[nextState]) return;
    state = nextState;
    robot.dataset.state = nextState;
    stopTalking();
    if (nextState === "working") startTalking();
    else setMouth(MOUTH_SHAPES[nextState]);
    if (nextState === "sleep" && eyes) eyes.style.transform = "translate(0px, 0px)";
  }

  function doBlink() {
    if (destroyed || state === "sleep" || isBlinking) return;
    isBlinking = true;
    robot.classList.add("blink");
    window.setTimeout(() => {
      robot.classList.remove("blink");
      isBlinking = false;
    }, 115);
  }

  function scheduleBlink() {
    window.clearTimeout(blinkTimer);
    if (destroyed) return;
    blinkTimer = window.setTimeout(() => {
      if (state !== "sleep") {
        doBlink();
        if (!reducedMotion.matches && Math.random() < 0.18) window.setTimeout(doBlink, 260);
      }
      scheduleBlink();
    }, 2200 + Math.random() * 3600);
  }

  function onPointerMove(event) {
    if (destroyed || state === "sleep" || isBlinking || !stage || !eyes) return;
    const rect = robot.getBoundingClientRect();
    const stageRect = stage.getBoundingClientRect();
    const dx = (event.clientX - (rect.left + rect.width / 2)) / Math.max(stageRect.width / 2, 1);
    const dy = (event.clientY - (rect.top + rect.height / 2)) / Math.max(stageRect.height / 2, 1);
    const x = Math.max(-1, Math.min(1, dx)) * 3.2;
    const y = Math.max(-1, Math.min(1, dy)) * 2.1;
    eyes.style.transform = `translate(${x}px, ${y}px)`;
  }

  const resetEyes = () => {
    if (eyes) eyes.style.transform = "translate(0px, 0px)";
  };

  const statusObserver = status ? new MutationObserver(() => applyState(statusToState(status.textContent))) : null;
  statusObserver?.observe(status, { childList: true, subtree: true, characterData: true });
  stage?.addEventListener("pointermove", onPointerMove);
  stage?.addEventListener("pointerleave", resetEyes);

  applyState(statusToState(status?.textContent));
  scheduleBlink();

  return {
    setState(nextState) {
      const normalized = String(nextState || "").trim().toLowerCase();
      applyState(normalized === "talking" ? "working" : normalized);
    },
    blink: doBlink,
    speak(enabled = true) { applyState(enabled ? "working" : "idle"); },
    getState() { return state; },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      window.clearTimeout(blinkTimer);
      stopTalking();
      statusObserver?.disconnect();
      stage?.removeEventListener("pointermove", onPointerMove);
      stage?.removeEventListener("pointerleave", resetEyes);
      robot.classList.remove("blink", "utel-robot-face", "utel-robot-png-face");
    },
  };
}

export function initializeDashboardRobot() {
  if (activeRobot) return activeRobot;
  const robot = document.querySelector("#view-dashboard .execution-radar .robot-core");
  if (!robot) return null;
  installStylesheet();
  buildFace(robot);
  activeRobot = createRobotController(robot);
  window.UTELRobot = activeRobot;
  return activeRobot;
}

window.addEventListener("beforeunload", () => activeRobot?.destroy?.(), { once: true });
