function fillProfile(me) {
  document.getElementById("p-avatar").textContent = initial(me);
  document.getElementById("p-name").textContent = displayName(me);

  var joined = new Date(me.created_at.replace(" ", "T") + "Z");
  document.getElementById("p-meta").textContent =
    "@" + me.username + " - " + (me.role === "teacher" ? "Teacher" : "Student") +
    " - Member since " + joined.toLocaleDateString();
  document.getElementById("p-bio").textContent = me.bio;

  document.getElementById("f-name").value = me.full_name;
  document.getElementById("f-email").value = me.email;
  document.getElementById("f-bio").value = me.bio;
}

lmsReady.then(fillProfile);

document.getElementById("profile-form").onsubmit = function (e) {
  e.preventDefault();
  var msg = document.getElementById("p-msg");
  msg.textContent = "Saving...";
  api("POST", "/api/profile", {
    full_name: document.getElementById("f-name").value,
    email: document.getElementById("f-email").value,
    bio: document.getElementById("f-bio").value
  }).then(function (r) {
    if (!r.ok) {
      msg.textContent = r.data.error || "Could not save.";
      return;
    }
    lmsMe = r.data;
    fillProfile(r.data);
    buildSidebar(r.data);
    refreshTodos();
    msg.textContent = "Saved!";
  }).catch(function () {
    msg.textContent = "Could not reach the server.";
  });
};