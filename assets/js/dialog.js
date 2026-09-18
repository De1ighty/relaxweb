/* 页面内二次确认弹层：替代原生 alert / confirm。
   原生弹窗会阻塞浏览器主线程，Playwright 之类的自动化测试会一直卡在对话框上，
   所以前端统一用这里的 DOM 浮层，接口保持 Promise 语义：

     alertDialog(message, options)   → 确定后 resolve()
     confirmDialog(message, options) → 确定 resolve(true)，取消 resolve(false)

   options: { title, confirmText, cancelText, tone: "default" | "danger" }

   自动化测试可用的 DOM 契约：
     #liveDialog、.live-dialog-message、.live-dialog-confirm、.live-dialog-cancel；
     弹层显示期间 body[data-dialog-open="true"]。

   直播间页面还是经典脚本，由 js/dialog-global.js 把这两个函数挂到 window.LiveDialog。 */

const DEFAULT_CONFIRM = "确定";
const DEFAULT_CANCEL = "取消";

let current = null; // 正在显示的弹层
const pending = []; // 排队中的请求：连发多条提示时逐个显示，不要叠在一起

function buildDialog({ kind, title, message, confirmText, cancelText, tone }) {
  const overlay = document.createElement("div");
  overlay.className = "live-dialog";
  overlay.id = "liveDialog";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");

  const card = document.createElement("div");
  card.className = "live-dialog-card";
  if (tone === "danger") card.classList.add("is-danger");

  if (title) {
    const head = document.createElement("div");
    head.className = "live-dialog-title";
    head.textContent = title;
    card.append(head);
  }
  const text = document.createElement("div");
  text.className = "live-dialog-message";
  text.textContent = message;
  card.append(text);

  const actions = document.createElement("div");
  actions.className = "live-dialog-actions";
  let cancelButton = null;
  if (kind === "confirm") {
    cancelButton = document.createElement("button");
    cancelButton.className = "live-dialog-cancel";
    cancelButton.type = "button";
    cancelButton.textContent = cancelText;
    actions.append(cancelButton);
  }
  const confirmButton = document.createElement("button");
  confirmButton.className = "live-dialog-confirm";
  confirmButton.type = "button";
  confirmButton.textContent = confirmText;
  actions.append(confirmButton);

  card.append(actions);
  overlay.append(card);
  return { overlay, confirmButton, cancelButton };
}

function open(request) {
  const { overlay, confirmButton, cancelButton } = buildDialog(request);
  current = request;

  const finish = (value) => {
    if (current !== request) return;
    current = null;
    document.removeEventListener("keydown", onKeydown, true);
    overlay.remove();
    if (!pending.length) delete document.body.dataset.dialogOpen;
    request.resolve(value);
    const next = pending.shift();
    if (next) open(next);
  };
  const onKeydown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      finish(request.kind === "confirm" ? false : undefined);
    } else if (event.key === "Enter" && !event.isComposing) {
      event.preventDefault();
      finish(request.kind === "confirm" ? true : undefined);
    }
  };

  confirmButton.addEventListener("click", () => finish(request.kind === "confirm" ? true : undefined));
  cancelButton?.addEventListener("click", () => finish(false));
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) finish(request.kind === "confirm" ? false : undefined);
  });
  document.addEventListener("keydown", onKeydown, true);

  document.body.dataset.dialogOpen = "true";
  document.body.append(overlay);
  confirmButton.focus({ preventScroll: true });
}

function request(kind, message, options = {}) {
  const { title = "", confirmText = DEFAULT_CONFIRM, cancelText = DEFAULT_CANCEL, tone = "default" } = options;
  return new Promise((resolve) => {
    const item = { kind, title, message: String(message ?? ""), confirmText, cancelText, tone, resolve };
    if (current) pending.push(item);
    else open(item);
  });
}

/** 只有确定按钮的提示框（替代 alert）。 */
export function alertDialog(message, options) {
  return request("alert", message, options);
}

/** 确定/取消的确认框（替代 confirm），确定 resolve(true)。 */
export function confirmDialog(message, options) {
  return request("confirm", message, options);
}

/** 当前是否有弹层在显示（测试与键盘处理用）。 */
export function dialogOpen() {
  return Boolean(current);
}
