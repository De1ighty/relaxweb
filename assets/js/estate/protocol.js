"use strict";

import { elements, send, state, updateCoinChip } from "../core.js";
import { alertDialog } from "../dialog.js";
import { onMessage } from "../registry.js";
import { clearEstate, estateStore, setEstateSnapshot } from "./state.js";

let sequence = 0;

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
  if (!send({ type, request_id: id, ...payload })) estateStore.pending.delete(id);
  return id;
}

onMessage("estate_state", (data) => {
  if (data.request_id) estateStore.pending.delete(data.request_id);
  setEstateSnapshot(data);
  if (state.currentUser) {
    state.currentUser.coins = data.coins;
    updateCoinChip();
  }
});

onMessage("estate_error", (data) => {
  if (data.request_id) estateStore.pending.delete(data.request_id);
  if (data.state) setEstateSnapshot(data.state);
  void alertDialog(data.message || "庄园操作失败");
});

document.addEventListener("authstatechange", ({ detail }) => {
  if (!detail.user) {
    clearEstate();
    return;
  }
  if (state.hallPage === "estate") requestEstate();
});

export function pendingEstateAction() {
  return estateStore.pending.size > 0;
}
