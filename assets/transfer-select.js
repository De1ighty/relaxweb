"use strict";

/* 转账目标选择组件：拉取注册用户，按昵称首字母（拼音序）排序，
   每项展示缩小头像、昵称与用户名；选中后写进隐藏输入框。
   两处财务弹窗（直播间 / 游戏厅）共用。 */

const TransferSelect = (() => {
  const state = {
    parts: null,
    onRequest: null,
    getSelf: null,
    users: [],
    selected: null,
  };

  const $ = (id) => document.getElementById(id);

  function avatarNode(user, sizeClass) {
    const av = document.createElement("span");
    av.className = `user-select-avatar ${sizeClass || ""}`;
    if (user.avatar) {
      const image = document.createElement("img");
      image.src = user.avatar;
      image.alt = "";
      av.append(image);
    } else {
      av.textContent = (user.nickname || user.username).charAt(0).toUpperCase();
    }
    return av;
  }

  function renderList() {
    const list = state.parts.list;
    list.replaceChildren();
    if (!state.users.length) {
      const empty = document.createElement("div");
      empty.className = "user-select-empty";
      empty.textContent = "没有可选的用户";
      list.append(empty);
      return;
    }
    const selfName = state.getSelf ? state.getSelf() : null;
    for (const user of state.users) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "user-select-item";
      if (selfName && user.username === selfName) {
        row.disabled = true;
        row.title = "不能转账给自己";
      }
      row.append(avatarNode(user));
      const meta = document.createElement("span");
      meta.className = "user-select-meta";
      const name = document.createElement("span");
      name.className = "user-select-name";
      name.textContent = user.nickname || user.username;
      meta.append(name);
      if (user.nickname && user.nickname !== user.username) {
        const id = document.createElement("span");
        id.className = "user-select-id";
        id.textContent = user.username;
        meta.append(id);
      }
      row.append(meta);
      row.addEventListener("click", () => select(user));
      list.append(row);
    }
  }

  function updateToggle() {
    const toggle = state.parts.toggle;
    toggle.replaceChildren();
    if (state.selected) {
      toggle.append(avatarNode(state.selected, "small"));
      const name = document.createElement("span");
      name.className = "user-select-chosen";
      name.textContent = state.selected.nickname || state.selected.username;
      toggle.append(name);
    } else {
      const placeholder = document.createElement("span");
      placeholder.className = "user-select-placeholder";
      placeholder.textContent = "选择转账对象…";
      toggle.append(placeholder);
    }
  }

  function select(user) {
    state.selected = user;
    state.parts.hidden.value = user.username;
    close();
    updateToggle();
  }

  function open() {
    state.parts.menu.hidden = false;
    if (!state.users.length) requestUsers();
  }

  function close() {
    state.parts.menu.hidden = true;
  }

  function requestUsers() {
    state.onRequest?.();
  }

  function setUsers(users) {
    // 排序由服务端完成（昵称首字母拼音序），前端按原样展示
    state.users = users || [];
    renderList();
  }

  function reset() {
    state.selected = null;
    state.parts.hidden.value = "";
    updateToggle();
  }

  function init(parts, onRequest, getSelf) {
    state.parts = parts;
    state.onRequest = onRequest;
    state.getSelf = getSelf;
    parts.toggle.addEventListener("click", () => {
      if (parts.menu.hidden) {
        open();
        requestUsers();
      } else {
        close();
      }
    });
    document.addEventListener("click", (event) => {
      if (!parts.toggle.parentElement.contains(event.target)) close();
    });
    updateToggle();
  }

  return {
    init,
    setUsers,
    requestUsers,
    reset,
    get selected() {
      return state.selected;
    },
  };
})();
