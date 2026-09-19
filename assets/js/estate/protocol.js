"use strict";

import { elements, send, state, updateCoinChip } from "../core.js";
import { alertDialog } from "../dialog.js";
import { onMessage } from "../registry.js";
import { clearEstate, estateStore, setEstateSnapshot } from "./state.js";

let sequence = 0;
const waiters = new Map();

function requestId(prefix) {
  sequence += 1;
  return `${prefix}-${Date.now().toString(36)}-${sequence.toString(36)}`;
}

export function requestEstate() {
  if (state.currentUser) send({ type: "get_estate" });
}

export function estateCommand(type, payload = {}) {
  const id = requestId(type.replace("estate_", ""));
  estateStore.pending.set(id, { type, at: Date.now() });
  if (!send({ type, request_id: id, ...payload })) {
    estateStore.pending.delete(id);
    return null;
  }
  return id;
}

export function estateRequest(type, payload = {}) {
  const id = estateCommand(type, payload);
  if (!id) return Promise.reject(new Error("游戏厅尚未连接"));
  return new Promise((resolve, reject) => waiters.set(id, { resolve, reject }));
}

onMessage("estate_state", (data) => {
  if (data.request_id) estateStore.pending.delete(data.request_id);
  if (data.request_id && waiters.has(data.request_id)) {
    waiters.get(data.request_id).resolve(data.result);
    waiters.delete(data.request_id);
  }
  setEstateSnapshot(data);
  if (state.currentUser) {
    state.currentUser.coins = data.coins;
    updateCoinChip();
  }
});

onMessage("estate_error", (data) => {
  if (data.request_id) estateStore.pending.delete(data.request_id);
  if (data.request_id && waiters.has(data.request_id)) {
    waiters.get(data.request_id).reject(new Error(data.message || "庄园操作失败"));
    waiters.delete(data.request_id);
  }
  if (data.state) setEstateSnapshot(data.state);
  void alertDialog(data.message || "庄园操作失败");
});

document.addEventListener("authstatechange", ({ detail }) => {
  if (!detail.user) {
    for (const waiter of waiters.values()) waiter.reject(new Error("登录已结束"));
    waiters.clear();
    clearEstate();
    return;
  }
  if (state.hallPage === "estate") requestEstate();
});

export function pendingEstateAction() {
  return estateStore.pending.size > 0;
}
