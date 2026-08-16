/* ============================================================
   Сэмпл шага (pl_tile4, Counter-Strike), вшит прямо в страницу:
   внешние файлы артефакту загружать нельзя.
   ============================================================ */

const STEP_MP3 =
  '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' +
  'BoQKRkyPZjmMJlODBhYDRtVAZokbhtiDpru9hhouJgUPhhoOhiAEJjsHpgoAIWA8QhOYNhSFgGAQYQEaFJEZ2FeZonAYLmiDhHMNgTMBgaMK' +
  'gIMKQDMCggRxmWX2///9B6Lc//+0OBA14RMmZz41QxRRIkYWSWcEgyVBwxQFVMTCINAZezZ4Uy40XXUxKTqboImNqbHMBrWIXNZIgB80Oqsx' +
  'VUz97iJyAFIZxH7CyWLgwrOHyAkwuSJI0DT2/ZWsEoE6qxVKWXMLgJylVWYw/aXM87XYzKb92mypgdpVTEFNRTMuMTAwVVVVVVVVVVVVVVVV' +
  'VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVO3BIqP0UdRiR5GUa' +
  'wbbQZmgym0AYZHDxi0YI9Dpw0Ng8pc4YwFJT//uSZPYAB54uxwZ7oAIAAA0gwAAADtCZLj28ABAAADSDgAAEMUTTFTPzgpsOKCfcZJnSvgOg' +
  'HKTfqDSFzoCTNigyUTOAEOAT884gsBzDkzhATCizMqDJmDOAAIpMkbMGoQHEQg6QjeD/Q1A6mwrWYmJxBnPuMUE1IOTOJA3xjUKB4wdyBISA' +
  's4AwsmKnl8zKBCxJfov81ti7bPtRz2ppJIRlAYraoJILLlEzaAmUp0JYBx0JKbbIpCsHQrwdJEpSpDIuUpSpSXNjaqyb7NWWJLkKWsrZcdNB' +
  'uy+YZUhAC52WvO7zP4lTK0LxYehjDMAszXdMO8VhbeIw6u54JCySLPw/sVlFitTVBJLbt19u3+616Ho3Uqu6e96mVW1p969aFUxBTUUzLjEw' +
  'MFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVQlYAELnBo+Z8WoGXZrRmmUEwYmKZiTRoJBjBwAKGEAgUiY8McEO' +
  'QGjQsDUlxJqRAQILHiBiUhkQQy1FBwiOq2mOamwHgJoYwYLIghwAx//7kmTSjvUMKMaDmspyAAANIAAAARA4mS5tYwAQAAA0gAAABILWGYog' +
  'NBfYWeDbwCAYVJpnhpQk4DhwYwws0VjiaJjjZGEryFk2CJ01URkMVWODBhyfptCBCAswYxRcRlpewxAQaApZGnccSYpKTuBTHwBWKBw6+UDZ' +
  'hFOuTTsxM7x86pwyjsPDjKM4jA4ScxIQSGBzwzAkERzjmzavDLUDHQQKJNcYMEIBbJkRuIAAymbMG2LmqWhnwwhkJumjmipwlUmpPkQcdym2' +
  'XHOJHCLjLM2sRaxt3piR5naEmNKsA1QzBUAgB0kBlBtI4JGBY4AmgKPA2ICWZj7AhEIzgIiTGqYxQEvAl4XKxbDDVudgWjvK//9i/0PoHqs/' +
  '9X0/61JMQU1FMy4xMDCqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqj4A9MZigx5sDRodNcFg' +
  'zYTzI2jHSTZHgrVNFsx0DPQLolFxq3HAGIUD0EF5UHE7waMbVyChxiiZY4GceKYxTqbZxgn/+5Jk5g70zyjGg5rJ8gAADSAAAAEWGKUWTm9C' +
  'AAAANIAAAAQjnZjvgVs/njKLbqa5wKrNyY5lQoSeIQFZLUmfmS2ikZkmnC2ZbpFudIYIkNiEX1FBgjE5aBAKBpSlIQUlzwwcRxPaWBwFlGH8' +
  'CgbH6Zjsrp6Ml//////////6XnUA+YaA5iFUGaVyYeGdVCCE4qKMpCNqkGqgV6PVsZN4IBUC54IAHBQh4wjDGUA3RsgmFCI2kaiqCdJJJUOM' +
  'CoZnUGqYRDgJVM0wgA8IXuQzGoREIvoaiLXmO8DuwdmLNG6yFijYeM9YL1opxA0nw2ka5NO017wQOMuGOuCTTiGtoygpkyTSUdLMFBpzQrjg' +
  'T8/eT/vZs+pv/W3/1Ve3u/UiTEFNRTMuMTAwqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqjoA' +
  'cMRhMzYhDA6rG1YQANUdEgg84OcQBSAUFGYAgAMYOIUJDhJpFmy8ZKYhhNKI2QQEgIrBCwdXxt2qVmeyCxTXWPM0//uSZOCO9PIoRYOayRAA' +
  'AA0gAAABFDCjGC5rIpAAADSAAAAEUzEuSqWnWbbRikg5c0ViJ4QMCL4jbNkkG6HC6SojVrSQXkF0DHnECpjSlB5zIqWmckJhhYtVYwBwUAbJ' +
  'DWgBEDSSU5hhikll3UUJZOvyrGQI/oLjDZwNcBTg44zOY7rczvkxFk1jsZQnDuAFmBBAGQDt83TI2hEqGzUBTIHhrAIGBvypmCBzzwiDmcSB' +
  'y82588Kkz5Q9VE1fE20MC5jkPgqjN0pOOBKL5sgKNglFASowSA1so2ccGRBGrBCM/zcE4g4oaWyY6OAjxmUQ0eMMfM0mZcbFSgGHlByBhoxZ' +
  'tgpf4KL5AOAwqVBQ9KKYJg0MtKhuICP/p//Mf//++jhAXQHGPBQZABpgs1mDA0BiYYGCpEFAcE0lwCBzBILBgeMCgQwkCAEJTBZOMcjGnYQP' +
  'M2jAhYy4I4hMaOmYEJAGaJqRdceWmHbFRiageYA6F0BggYKejhoaKmzagQqVA4JAGFfkQwwTAQNjBAUPUkDIlzQMDCvCEKFCAADmrYl7DP/7' +
  'kmThD/SmJ8YDmsjCAAANIAAAARV4oRIOb0AAAAA0gAAABPjzGFDQBVLzDAkIzABzFD28JRRIOQPTLKAitNA16NbsKACBOViaMcC4ORhLB1cG' +
  'pDlgaBTHIWjC8JjEwPTJQHzGsTjCULDPIdzD4TTDIF17JRGAoRGaxsZmbBiZGmcS4YEEZiwPmmw6FVAaqZpgIvmlT+ZOAJhIbmGyAYdGZgUH' +
  'mFCWYLFpwA7mJjIYwGBCODIgQMwBUyIdTGw0M1j4DSEw8DxwzkyRMPDMwGCyQXGOgWYnNohBwsIjFgvBgCMEjgxiDTBpbMuCsHQ8eOINBBKC' +
  'zKgbM9IM04TjEYkR3MCA4yIETFBJMPAYxaNAoBVeLfv6wx56hc9lrmvge7cu0tzF6z6gcEkHGhsETRk5D4ZjmOfGKBwVFAMevawJnri66kKm' +
  'zqAqNQu9//5Vv/4STEFNRTMuMTAwqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq' +
  'qqqqqqqqqqqqqqr/+5Jk/4AFDihGhXNAAAAADSCgAAEhqMcQOd4AAAAANIMAAACqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq' +
  'qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq' +
  'qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqAAADlEYDXI6yNpEkm4pCqCtdtRFyXds1qa1/8JXK5mlTpyocorp0tqErwkwOYhLp' +
  'iQ5DnJEi2iGo5EmioZFczRpU8cyihp1QthKhNjpgK58eUDI0FdYK//PfPZ5P/0dZ3iXrOoxLO/iKTEFNRTMuMTAwqqqqqqqqqqqqqqqqqqqq' +
  'qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq' +
  'qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq//uSZHUP80YhwB9h4AAAAA0g4AABAAABpAAAACAAADSAAAAEqqqqqqqqqqqqqqqqqqqqqqqqqqqq' +
  'qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq' +
  'qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq' +
  'qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq' +
  'qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq' +
  'qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqg==';

/** base64 -> ArrayBuffer, без сети и без fetch. */
function decodeBase64(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}
