/* 直播间页面（index.html）仍在用经典脚本 app.js，没法 import ES 模块，
   这里把 dialog.js 挂到 window.LiveDialog，两个页面共用同一份弹层实现。 */

import { alertDialog, confirmDialog } from "./dialog.js";

window.LiveDialog = { alert: alertDialog, confirm: confirmDialog };
