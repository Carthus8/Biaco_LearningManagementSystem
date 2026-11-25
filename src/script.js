// ---------- Data (replace with API calls later) ----------
var courses = [
  {
    id: 1,
    title: "Intro to Web Development",
    lessons: [
      { id: 1, title: "What is HTML?", content: "HTML structures content on the web." },
      { id: 2, title: "Styling with CSS", content: "CSS controls layout and appearance." },
      { id: 3, title: "JavaScript Basics", content: "JavaScript adds interactivity." }
    ]
  },
  {
    id: 2,
    title: "Basic Mathematics",
    lessons: [
      { id: 1, title: "Fractions", content: "A fraction represents a part of a whole." },
      { id: 2, title: "Decimals", content: "Decimals are another way to write fractions." }
    ]
  }
];

// ---------- State ----------
var user = localStorage.getItem("lms_user");
var progress = JSON.parse(localStorage.getItem("lms_progress") || "{}");
var currentCourse = null;
var currentLesson = null;

// ---------- Helpers ----------
function $(id) {
  return document.getElementById(id);
}

var views = ["login", "courses", "course", "progress"];

function show(name) {
  for (var i = 0; i < views.length; i++) {
    $("view-" + views[i]).hidden = views[i] !== name;
  }
}

function saveProgress() {
  localStorage.setItem("lms_progress", JSON.stringify(progress));
}

function getDone(courseId) {
  if (progress[user] && progress[user][courseId]) {
    return progress[user][courseId];
  }
  return [];
}

function isDone(courseId, lessonId) {
  return getDone(courseId).indexOf(lessonId) !== -1;
}

// ---------- Auth ----------
function login(name) {
  user = name;
  localStorage.setItem("lms_user", name);
  renderCourses();
}

function logout() {
  localStorage.removeItem("lms_user");
  user = null;
  show("login");
}

// ---------- Renderers ----------
function renderCourses() {
  var list = $("course-list");
  list.innerHTML = "";
  courses.forEach(function (c) {
    var li = document.createElement("li");
    li.textContent = c.title;
    li.onclick = function () {
      openCourse(c);
    };
    list.appendChild(li);
  });
  show("courses");
}

function openCourse(course) {
  currentCourse = course;
  currentLesson = null;
  $("course-title").textContent = course.title;
  openLesson(course.lessons[0]);
  show("course");
}

function renderLessonList() {
  var list = $("lesson-list");
  list.innerHTML = "";
  currentCourse.lessons.forEach(function (l) {
    var li = document.createElement("li");
    li.textContent = l.title;
    if (currentLesson && currentLesson.id === l.id) {
      li.classList.add("active");
    }
    if (isDone(currentCourse.id, l.id)) {
      li.classList.add("done");
    }
    li.onclick = function () {
      openLesson(l);
    };
    list.appendChild(li);
  });
}

function openLesson(lesson) {
  currentLesson = lesson;
  $("lesson-title").textContent = lesson.title;
  $("lesson-content").textContent = lesson.content;
  renderLessonList();
}

function renderProgress() {
  var list = $("progress-list");
  list.innerHTML = "";
  courses.forEach(function (c) {
    var done = getDone(c.id).length;
    var pct = Math.round((done / c.lessons.length) * 100);
    var li = document.createElement("li");

    var label = document.createElement("strong");
    label.textContent = c.title + " - " + pct + "%";

    var bar = document.createElement("progress");
    bar.value = pct;
    bar.max = 100;

    li.appendChild(label);
    li.appendChild(document.createElement("br"));
    li.appendChild(bar);
    list.appendChild(li);
  });
  show("progress");
}

// ---------- Events ----------
$("login-form").onsubmit = function (e) {
  e.preventDefault();
  var name = $("username").value.trim();
  if (name) {
    login(name);
  }
};

$("complete-btn").onclick = function () {
  if (!progress[user]) {
    progress[user] = {};
  }
  if (!progress[user][currentCourse.id]) {
    progress[user][currentCourse.id] = [];
  }
  var done = progress[user][currentCourse.id];
  if (done.indexOf(currentLesson.id) === -1) {
    done.push(currentLesson.id);
  }
  saveProgress();
  renderLessonList();
};

$("back-to-courses").onclick = renderCourses;

$("nav-courses").onclick = function () {
  if (user) {
    renderCourses();
  }
};

$("nav-progress").onclick = function () {
  if (user) {
    renderProgress();
  }
};

$("nav-logout").onclick = logout;

// ---------- Init ----------
if (user) {
  renderCourses();
} else {
  show("login");
}