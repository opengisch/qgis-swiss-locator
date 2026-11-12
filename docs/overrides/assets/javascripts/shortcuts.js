// The pages write the shortcuts as on Windows and Linux: ++ctrl+k++. On macOS,
// QGIS takes Cmd for Ctrl and Option for Alt, and the key is called Return:
// show them so.

var KEYS_OF_MACOS = {
  "key-control": ["key-command", "Cmd"],
  "key-alt": ["key-option", "Option"],
  "key-enter": ["key-enter", "Return"],
}

if (/^mac/i.test((navigator.userAgentData || navigator).platform || "")) {
  // Again on each page, with instant navigation
  document$.subscribe(function () {
    document.querySelectorAll(".keys kbd").forEach(function (kbd) {
      var key = KEYS_OF_MACOS[kbd.className]
      if (key) {
        kbd.className = key[0]
        kbd.textContent = key[1]
      }
    })
  })
}
