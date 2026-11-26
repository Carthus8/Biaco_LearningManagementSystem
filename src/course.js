var match = window.location.search.match(/[?&]id=(\d+)/);
var courseId = match ? match[1] : null;
var isTeacher = false;
var firstLoad = true;

function uploadAll(activityId, fileList) {
  var files = Array.prototype.slice.call(fileList);
  var errors = [];
  var chain = Promise.resolve();
  files.forEach(function (f) {
    chain = chain.then(function () {
      return uploadFile(activityId, f).then(
        function (r) {
          if (!r.ok) { errors.push(f.name + ": " + (r.data.error || "failed")); }
        },
        function () { errors.push(f.name + ": network error"); }
      );
    });
  });
  return chain.then(function () { return errors; });
}

function renderFile(f) {
  var li = document.createElement("li");
  var chip = el("button", "file-chip", f.name + " (" + formatSize(f.size) + ")");
  chip.type = "button";
  chip.onclick = function () { downloadFile(f); };
  li.appendChild(chip);
  if (isTeacher) {
    var x = el("button", "file-x", "\u00d7");
    x.type = "button";
    x.title = "Remove file";
    x.onclick = function () {
      if (confirm("Remove " + f.name + "?")) {
        api("DELETE", "/api/files/" + f.id).then(loadActivities);
      }
    };
    li.appendChild(x);
  }
  return li;
}

function renderActivity(a) {
  var card = el("article", "card activity" + (a.done ? " done" : ""));

  var head = el("div", "activity-head");
  head.appendChild(el("h3", "", a.title));
  var info = dueInfo(a.due_date);
  head.appendChild(el("span", "pill " + (a.done ? "ok" : info.cls), a.done ? "Done" : info.text));
  card.appendChild(head);

  if (a.description) { card.appendChild(el("p", "desc", a.description)); }

  if (a.files.length) {
    var ul = el("ul", "files");
    a.files.forEach(function (f) { ul.appendChild(renderFile(f)); });
    card.appendChild(ul);
  }

  var actions = el("div", "actions");
  var doneBtn = el("button", "btn " + (a.done ? "btn-ghost" : "btn-primary"),
                   a.done ? "Mark as not done" : "Mark as done");
  doneBtn.type = "button";
  doneBtn.onclick = function () {
    api("POST", "/api/activities/" + a.id + "/done", { done: !a.done }).then(function () {
      loadActivities();
      refreshTodos();
    });
  };
  actions.appendChild(doneBtn);

  if (isTeacher) {
    var addLabel = el("label", "btn btn-ghost", "Add file");
    var input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.hidden = true;
    input.onchange = function () {
      uploadAll(a.id, input.files).then(function (errors) {
        if (errors.length) { alert(errors.join("\n")); }
        loadActivities();
      });
    };
    addLabel.appendChild(input);
    actions.appendChild(addLabel);

    var del = el("button", "btn btn-danger", "Delete");
    del.type = "button";
    del.onclick = function () {
      if (confirm("Delete this activity and its files?")) {
        api("DELETE", "/api/activities/" + a.id).then(function () {
          loadActivities();
          refreshTodos();
        });
      }
    };
    actions.appendChild(del);
  }

  card.appendChild(actions);
  return card;
}

function loadActivities() {
  return api("GET", "/api/courses/" + courseId + "/activities").then(function (r) {
    var title = document.getElementById("course-title");
    if (!r.ok) {
      title.textContent = "Course not found";
      return;
    }
    title.textContent = r.data.course.title;
    document.getElementById("course-desc").textContent = r.data.course.description;
    document.title = r.data.course.title + " - Student Learning Management System";

    var list = document.getElementById("activity-list");
    list.innerHTML = "";
    list.className = firstLoad ? "stagger" : "";
    firstLoad = false;

    if (!r.data.activities.length) {
      list.appendChild(el("p", "muted", "No activities posted yet."));
    }
    r.data.activities.forEach(function (a) {
      list.appendChild(renderActivity(a));
    });
  });
}

lmsReady.then(function (me) {
  isTeacher = me.role === "teacher";
  document.getElementById("post-box").hidden = !isTeacher;
  if (!courseId) {
    document.getElementById("course-title").textContent = "Course not found";
    return;
  }
  loadActivities();
});

// Refresh when a to-do is ticked in the sidebar
document.addEventListener("lms-changed", function () {
  if (courseId) { loadActivities(); }
});

document.getElementById("post-form").onsubmit = function (e) {
  e.preventDefault();
  var form = e.target;
  var btn = document.getElementById("post-btn");
  var msg = document.getElementById("post-msg");
  btn.disabled = true;
  msg.textContent = "Posting...";

  api("POST", "/api/courses/" + courseId + "/activities", {
    title: document.getElementById("act-title").value,
    description: document.getElementById("act-desc").value,
    due_date: document.getElementById("act-due").value
  }).then(function (r) {
    if (!r.ok) {
      msg.textContent = r.data.error || "Could not post.";
      btn.disabled = false;
      return;
    }
    return uploadAll(r.data.id, document.getElementById("act-files").files).then(function (errors) {
      msg.textContent = errors.length ? "Posted, but some files failed: " + errors.join("; ") : "Posted!";
      form.reset();
      btn.disabled = false;
      loadActivities();
      refreshTodos();
    });
  }).catch(function () {
    msg.textContent = "Could not reach the server.";
    btn.disabled = false;
  });
};