let isPasswordVisible = false;
let isEyeActive = false;
let mouseX = 0;
let mouseY = 0;

function handleEyeMovement(e) {
  if (!isPasswordVisible) return;
  mouseX = e.clientX;
  mouseY = e.clientY;
  updatePupilPosition();
}

function updatePupilPosition() {
  const eye = document.getElementById("passwordEye");
  if (!eye || !isPasswordVisible) return;

  const pupil = eye.querySelector(".pupil");
  const eyeRect = eye.getBoundingClientRect();
  const eyeCenterX = eyeRect.left + eyeRect.width / 2;
  const eyeCenterY = eyeRect.top + eyeRect.height / 2;

  const deltaX = mouseX - eyeCenterX;
  const deltaY = mouseY - eyeCenterY;
  const angle = Math.atan2(deltaY, deltaX);
  const distance = Math.min(8, Math.hypot(deltaX, deltaY) * 0.1);

  pupil.style.transform = `translate(
    ${Math.cos(angle) * distance}px,
    ${Math.sin(angle) * distance}px
  )`;
}

function togglePasswordVisibility(inputId) {
  const passwordInput = document.getElementById(inputId);
  const eye = document.getElementById("passwordEye");

  isPasswordVisible = !isPasswordVisible;
  passwordInput.type = isPasswordVisible ? "text" : "password";

  // Toggle eye states
  eye.querySelector(".eye-closed").style.display = isPasswordVisible
    ? "none"
    : "block";
  eye.querySelector(".eye-open").style.display = isPasswordVisible
    ? "block"
    : "none";

  if (isPasswordVisible) {
    document.addEventListener("mousemove", handleEyeMovement);
    updatePupilPosition();
  } else {
    document.removeEventListener("mousemove", handleEyeMovement);
    eye.querySelector(".pupil").style.transform = "translate(0, 0)";
  }
}

function showPasswordEye() {
  isEyeActive = true;
  const eye = document.getElementById("passwordEye");
  eye.style.opacity = "1";
  if (isPasswordVisible) updatePupilPosition();
}

function hidePasswordEye() {
  isEyeActive = false;
  const eye = document.getElementById("passwordEye");
  eye.style.opacity = "0.7";
  if (isPasswordVisible) {
    eye.querySelector(".pupil").style.transform = "translate(0, 0)";
  }
}

// Track mouse position globally
document.addEventListener("mousemove", (e) => {
  mouseX = e.clientX;
  mouseY = e.clientY;
});

// Close eye when clicking outside
document.addEventListener("click", (e) => {
  const passwordWrapper = document.querySelector(".password-input-wrapper");
  const eye = document.getElementById("passwordEye");

  if (!passwordWrapper.contains(e.target) && !eye.contains(e.target)) {
    hidePasswordEye();
  }
});
