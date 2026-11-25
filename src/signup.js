document.getElementById("signup-form").onsubmit = function (e) {
  e.preventDefault();
  var message = document.getElementById("message");
  var username = document.getElementById("username").value.trim();
  var password = document.getElementById("password").value;
  var confirm = document.getElementById("confirm").value;

  if (password !== confirm) {
    message.textContent = "Passwords do not match.";
    return;
  }

  fetch("/api/signup", {
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
        window.location.href = "login.html";
      } else {
        message.textContent = result.data.error;
      }
    })
    .catch(function () {
      message.textContent = "Could not reach the server.";
    });
};