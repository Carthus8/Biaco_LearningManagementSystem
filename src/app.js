var TOKEN_KEY = "lms_token";
var MAX_UPLOAD = 25 * 1024 * 1024;
var PUBLIC_PAGE = document.body.getAttribute("data-public") !== null;
var lmsMe = null;

// ---------- small helpers ----------
function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) { e.className = cls; }
  if (text !== undefined && text !== null) { e.textContent = text; }
  return e;
}

function never() {
  return new Promise(function () {});
}

function displayName(me) {
  return me.full_name || me.username;
}

function initial(me) {
  return displayName(me).charAt(0).toUpperCase();
}

function formatSize(n) {
  if (n < 1024) { return n + " B"; }
  if (n < 1048576) { return (n / 1024).toFixed(1) + " KB"; }
  return (n / 1048576).toFixed(1) + " MB";
}

function dueInfo(s) {
  if (!s) { return { text: "No due date", cls: "muted" }; }
  var p = s.split("-");
  var due = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
  var now = new Date();
  var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  var diff = Math.round((due - today) / 86400000);
  var nice = due.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  if (diff < 0) { return { text: "Overdue - " + nice, cls: "late" }; }
  if (diff === 0) { return { text: "Due today", cls: "soon" }; }
  if (diff === 1) { return { text: "Due tomorrow", cls: "soon" }; }
  if (diff <= 7) { return { text: "Due in " + diff + " days", cls: diff <= 2 ? "soon" : "ok" }; }
  return { text: "Due " + nice, cls: "ok" };
}

// ---------- page transitions ----------
function go(url) {
  if (document.body.classList.contains("leaving")) { return; }
  document.body.classList.add("leaving");
  setTimeout(function () { window.location.href = url; }, 250);
}

document.addEventListener("click", function (e) {
  if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey) { return; }
  var a = e.target.closest ? e.target.closest("a") : null;
  if (!a) { return; }
  var href = a.getAttribute("href");
  if (!href || href.charAt(0) === "#" || a.target === "_blank" || a.hasAttribute("download")) { return; }
  if (/^([a-z][a-z0-9+.\-]*:|\/\/)/i.test(href)) { return; }
  e.preventDefault();
  go(href);
});

window.addEventListener("pageshow", function () {
  document.body.classList.remove("leaving");
});

// ---------- server calls ----------
function authHeaders(extra) {
  var h = extra || {};
  var t = localStorage.getItem(TOKEN_KEY);
  if (t) { h["Authorization"] = "Bearer " + t; }
  return h;
}

function api(method, path, body) {
  var opts = { method: method, headers: authHeaders({}) };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  return fetch(path, opts).then(function (res) {
    return res.json().catch(function () { return {}; }).then(function (data) {
      if (res.status === 401 && !PUBLIC_PAGE) {
        localStorage.removeItem(TOKEN_KEY);
        go("login.html");
        return never();
      }
      return { ok: res.ok, status: res.status, data: data };
    });
  });
}

function uploadFile(activityId, file) {
  if (file.size > MAX_UPLOAD) {
    return Promise.resolve({ ok: false, data: { error: "Larger than 25 MB" } });
  }
  return fetch("/api/activities/" + activityId + "/files", {
    method: "POST",
    headers: authHeaders({
      "Content-Type": "application/octet-stream",
      "X-Filename": encodeURIComponent(file.name)
    }),
    body: file
  }).then(function (res) {
    return res.json().catch(function () { return {}; }).then(function (data) {
      return { ok: res.ok, data: data };
    });
  });
}

function downloadFile(f) {
  fetch("/api/files/" + f.id, { headers: authHeaders({}) })
    .then(function (res) {
      if (!res.ok) { throw new Error("download failed"); }
      return res.blob();
    })
    .then(function (blob) {
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = f.name;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
    })
    .catch(function () { alert("Could not download the file."); });
}

// ---------- sidebar (profile + to-do) ----------
function renderTodos(list) {
  var ul = document.getElementById("todo-list");
  if (!ul) { return; }
  ul.innerHTML = "";
  if (!list.length) {
    ul.appendChild(el("li", "todo-empty", "Nothing upcoming. You're all caught up!"));
    return;
  }
  list.forEach(function (t) {
    var li = el("li", "todo rise");
    var box = document.createElement("input");
    box.type = "checkbox";
    box.title = "Mark as done";
    box.onchange = function () {
      api("POST", "/api/activities/" + t.id + "/done", { done: true }).then(function () {
        li.classList.add("gone");
        setTimeout(function () {
          refreshTodos();
          document.dispatchEvent(new Event("lms-changed"));
        }, 300);
      });
    };
    var body = el("a", "todo-body");
    body.href = "course.html?id=" + t.course_id;
    var info = dueInfo(t.due_date);
    body.appendChild(el("span", "todo-title", t.title));
    body.appendChild(el("span", "todo-due " + info.cls, t.course_title + " - " + info.text));
    li.appendChild(box);
    li.appendChild(body);
    ul.appendChild(li);
  });
}

function refreshTodos() {
  return api("GET", "/api/todos").then(function (r) {
    renderTodos(r.data.todos || []);
  });
}

function logout() {
  function finish() {
    localStorage.removeItem(TOKEN_KEY);
    go("login.html");
  }
  api("POST", "/api/logout").then(finish, finish);
}

function buildSidebar(me) {
  var side = document.getElementById("sidebar");
  if (!side) { return; }
  side.innerHTML = "";

  var brand = el("a", "brand", "Student Learning Management System");
  brand.href = "index.html";
  side.appendChild(brand);

  var card = el("a", "side-card profile-card rise");
  card.href = "profile.html";
  card.appendChild(el("div", "avatar", initial(me)));
  var info = el("div", "profile-info");
  info.appendChild(el("strong", "", displayName(me)));
  info.appendChild(el("span", "badge", me.role === "teacher" ? "Teacher" : "Student"));
  card.appendChild(info);
  side.appendChild(card);

  var nav = el("nav", "side-card nav rise");
  var file = window.location.pathname.split("/").pop() || "index.html";
  [["index.html", "Dashboard"], ["profile.html", "My Profile"]].forEach(function (item) {
    var a = el("a", "", item[1]);
    a.href = item[0];
    if (file === item[0] || (item[0] === "index.html" && file === "course.html")) {
      a.className = "active";
    }
    nav.appendChild(a);
  });
  side.appendChild(nav);

  var todo = el("section", "side-card rise");
  todo.appendChild(el("h3", "", "To-do"));
  var ul = el("ul", "todo-list");
  ul.id = "todo-list";
  todo.appendChild(ul);
  side.appendChild(todo);

  var out = el("button", "btn btn-ghost block", "Log out");
  out.type = "button";
  out.onclick = logout;
  side.appendChild(out);
}

// ---------- startup for logged-in pages ----------
var lmsReady = null;
if (!PUBLIC_PAGE) {
  if (!localStorage.getItem(TOKEN_KEY)) {
    go("login.html");
    lmsReady = never();
  } else {
    lmsReady = api("GET", "/api/me")
      .then(function (r) {
        if (!r.ok) { return never(); }
        lmsMe = r.data;
        buildSidebar(lmsMe);
        refreshTodos();
        return lmsMe;
      })
      .catch(function () {
        var c = document.getElementById("content");
        if (c) { c.textContent = "Could not reach the server. Is server.py running?"; }
        return never();
      });
  }
}

// ---------- footer (appears on every page) ----------
(function () {
  var footer = document.createElement("footer");
  footer.className = "site-footer";

  var line = document.createElement("div");
  line.className = "footer-line";
  line.appendChild(document.createElement("span")).className = "footer-dot";

  var name = document.createElement("p");
  name.className = "footer-name";
  name.textContent = "Rigil Kent O. Biaco";

  var course = document.createElement("p");
  course.className = "footer-course";
  course.textContent = "BSIT 3-3";

  var rights = document.createElement("p");
  rights.className = "footer-rights";
  rights.textContent = "\u00a9 " + new Date().getFullYear() + " All rights reserved.";

  footer.appendChild(line);
  footer.appendChild(name);
  footer.appendChild(course);
  footer.appendChild(rights);
  document.body.appendChild(footer);
})();