var message = document.getElementById("message");

// If a valid session already exists, skip the login page
var savedToken = localStorage.getItem("lms_token");
if (savedToken) {
  fetch("/api/me", { headers: { "Authorization": "Bearer " + savedToken } })
    .then(function (res) {
      if (res.ok) {
       go("index.html");
      } else {
        localStorage.removeItem("lms_token");
      }
    });
}

document.getElementById("login-form").onsubmit = function (e) {
  e.preventDefault();
  var username = document.getElementById("username").value.trim();
  var password = document.getElementById("password").value;

  fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: username, password: password })
  })
    .then(function (res) {
      return res.json().then(function (data) {
        return { ok: res.ok, data: data };
      });
    })
    .then(function (result) {
      if (result.ok) {
        localStorage.setItem("lms_token", result.data.token);
        go("index.html");
      } else {
        message.textContent = result.data.error;
      }
    })
    .catch(function () {
      message.textContent = "Could not reach the server.";
    });
};