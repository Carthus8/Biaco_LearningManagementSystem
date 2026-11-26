lmsReady.then(function (me) {
  document.getElementById("greeting").textContent = "Welcome back, " + displayName(me) + "!";

  api("GET", "/api/courses").then(function (r) {
    var grid = document.getElementById("course-grid");
    grid.innerHTML = "";
    r.data.courses.forEach(function (c) {
      var card = el("a", "card course-card");
      card.href = "course.html?id=" + c.id;
      card.appendChild(el("h3", "", c.title));
      card.appendChild(el("p", "muted", c.description));
      card.appendChild(el("span", "badge", c.activity_count + " activities"));
      grid.appendChild(card);
    });
  });
});