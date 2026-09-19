"use strict";

export const estateStore = {
  snapshot: null,
  selectedPlot: null,
  pending: new Map(),
  clockOffset: 0,
  listeners: new Set(),
};

export function setEstateSnapshot(data) {
  estateStore.snapshot = data;
  estateStore.clockOffset = Number(data.server_time || 0) * 1000 - Date.now();
  estateStore.listeners.forEach((listener) => listener(data));
}

export function clearEstate() {
  estateStore.snapshot = null;
  estateStore.selectedPlot = null;
  estateStore.pending.clear();
  estateStore.listeners.forEach((listener) => listener(null));
}

export function estateNow() {
  return Math.floor((Date.now() + estateStore.clockOffset) / 1000);
}

export function subscribeEstate(listener) {
  estateStore.listeners.add(listener);
  return () => estateStore.listeners.delete(listener);
}
