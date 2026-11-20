const params = new URLSearchParams(location.search);
const error = document.getElementById("login-error");
const username = document.getElementById("username");
const password = document.getElementById("password");
const toggle = document.getElementById("show-password");

if (params.get("error") === "credentials") {
  error.textContent = "El usuario o la contraseña son incorrectos.";
  error.hidden = false;
  username.setAttribute("aria-invalid", "true");
  password.setAttribute("aria-invalid", "true");
} else if (params.get("error") === "limit") {
  error.textContent = "Demasiados intentos. Espera un minuto y vuelve a intentarlo.";
  error.hidden = false;
}
if (!error.hidden) {
  username.setAttribute("aria-describedby", error.id);
  password.setAttribute("aria-describedby", error.id);
}
toggle.hidden = false;
toggle.addEventListener("click", () => {
  const show = password.type === "password";
  password.type = show ? "text" : "password";
  toggle.textContent = show ? "Ocultar" : "Mostrar";
});
