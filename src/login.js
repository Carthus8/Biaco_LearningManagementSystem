// If already logged in, skip the login page
if (localStorage.getItem("lms_user")) {
  window.location.href = "index.html";
}

document.getElementById("login-form").onsubmit = function (e) {
  e.preventDefault();
  var name = document.getElementById("username").value.trim();
  if (name) {
    localStorage.setItem("lms_user", name);
    window.location.href = "index.html";
  }
};