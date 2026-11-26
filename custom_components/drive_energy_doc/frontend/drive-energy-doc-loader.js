// Lädt das Panel bei jedem Öffnen frisch (am Browser-Cache vorbei): Änderungen am Panel sind dann ohne Neustart von Home Assistant sichtbar.
await import(`./drive-energy-doc-panel.js?t=${Date.now()}`);
