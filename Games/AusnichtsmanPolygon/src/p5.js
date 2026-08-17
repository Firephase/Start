/* ============================================================
   Три фигуры
   ============================================================ */

const BAND_R = 1.06;   // радиус средней окружности
const BAND_W = 0.34;   // половина ширины ленты

const SHAPES = [
  {
    name: 'Цилиндр', k: 0,
    home: [-7.8, 3.15, 1.4],
    faceA: [0.82, 0.85, 0.89], faceB: [0.44, 0.48, 0.55],
    spread: 0,
    pieces: [
      { side: 1,  offset: [0, 1.15, 0] },
      { side: -1, offset: [0, -1.15, 0] },
    ],
  },
  {
    name: 'Лента Мёбиуса', k: 1,
    home: [0, 3.62, -2.6],
    faceA: [0.86, 0.56, 0.29], faceB: [0.52, 0.28, 0.16],
    spread: 0.52,
    pieces: [
      { side: 1, offset: [0, 0, 0] },
    ],
  },
  {
    name: 'Двойной перекрут', k: 2,
    home: [7.8, 3.15, 1.4],
    faceA: [0.72, 0.72, 0.83], faceB: [0.41, 0.40, 0.53],
    spread: 0.52,
    pieces: [
      { side: 1,  offset: [0, 0, 0] },
      { side: -1, offset: [0, 0, 0] },
    ],
  },
];

for (const s of SHAPES) {
  s.progress = 0;     // сколько средней линии проведено, 0..1
  s.cut = 0;          // раскрытие разреза, 0..1
  s.cutTarget = 0;
  s.sep = 0;          // как далеко разведены куски, 0..1
  s.sepTarget = 0;
  s.rotY = 0.4; s.rotYTarget = 0.4;
  s.rotX = 0.12; s.rotXTarget = 0.12;
  s.zoom = 1; s.zoomTarget = 1;
  s.focus = 0;        // 0 — висит на месте, 1 — в руках
  s.phase = Math.random() * TAU;
  s.autoDraw = false;
  s.pos = [s.home[0], s.home[1], s.home[2]];
  s.grabPos = [s.home[0], s.home[1], s.home[2]];
}

/** Сетка (u, s) для одного куска ленты. */
function buildBandMesh(uMax, nu, nv) {
  const us = [], ss = [], idx = [];
  for (let i = 0; i <= nu; i++) {
    const u = (i / nu) * uMax;
    for (let j = 0; j <= nv; j++) {
      us.push(u);
      ss.push(j / nv);
    }
  }
  for (let i = 0; i < nu; i++) {
    for (let j = 0; j < nv; j++) {
      const a = i * (nv + 1) + j, b = a + nv + 1;
      idx.push(a, b, a + 1, a + 1, b, b + 1);
    }
  }
  return {
    u: buffer(new Float32Array(us)),
    s: buffer(new Float32Array(ss)),
    idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER),
    count: idx.length,
  };
}

const meshShort = buildBandMesh(TAU, 190, 9);        // цилиндр и двойной перекрут
const meshLong = buildBandMesh(TAU * 2, 330, 9);     // лента Мёбиуса — два круга

for (const s of SHAPES) {
  s.mesh = s.k === 1 ? meshLong : meshShort;
  s.hairs = buildHairs(s.k, BAND_R);
}

/* ============================================================
   Сцена
   ============================================================ */

const terrain = buildTerrain();
const solids = buildSolids();
const bushes = buildBushes();

const texGround = texture(makeGroundTexture());
const texBush = texture(makeBushTexture(), { mips: true });
const texShadow = texture(makeShadowTexture());
const texMilky = texture(makeMilkyTexture(), { wrapS: gl.REPEAT, wrapT: gl.CLAMP_TO_EDGE });
const labels = SHAPES.map((s) => ({
  tex: texture(makeLabelTexture(s.name)),
  quad: buildQuads([[s.home[0], s.home[1] + 1.85, s.home[2]]], () => 1.0),
}));
const shadows = buildQuads(
  SHAPES.map((s) => [s.home[0], terrainH(s.home[0], s.home[2]) + 0.03, s.home[2]]),
  () => 1.9
);
const quadScreen = buffer(new Float32Array([-1, -1, 3, -1, -1, 3]));
const rotor = buildRotor();
const hands = [buildHand(false), buildHand(true)];
const unitArrow = buildUnitArrow();
const tentMesh = buildTent();
const catMesh = buildCat();
const glowDot = buildGlow();
const rocketMesh = buildRocket('full');
const cockpitMesh = buildRocket('cockpit');
const sphereMesh = buildSphere();
const texPlanet = makePlanetTexture({ seed: 0, style: 0, home: PLANET_HOME });
const texGamma = makePlanetTexture({ seed: 37.4, style: 1, home: GAMMA.home, sea: 0.545, landBias: 0.02 });
const spaceRot = m4(), spaceTmp = m4();
initPairs();
const arrowModel = m4(), arrowFull = m4();
const water = buildWater();

/* Сцена рисуется в текстуру: пост-обработка гнёт её у чёрной дыры. */
const fbo = {
  fb: gl.createFramebuffer(),
  tex: gl.createTexture(),
  depth: gl.createRenderbuffer(),
  w: 0, h: 0,
};
gl.bindTexture(gl.TEXTURE_2D, fbo.tex);
gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);

function sizeFbo(w, h) {
  if (fbo.w === w && fbo.h === h) return;
  fbo.w = w; fbo.h = h;
  gl.bindTexture(gl.TEXTURE_2D, fbo.tex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
  gl.bindRenderbuffer(gl.RENDERBUFFER, fbo.depth);
  gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT16, w, h);
  gl.bindFramebuffer(gl.FRAMEBUFFER, fbo.fb);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, fbo.tex, 0);
  gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, fbo.depth);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
}

/* ============================================================
   Камера и состояние игры
   ============================================================ */

const cam = {
  x: 0, y: 0, z: 15.5,
  yaw: 0, pitch: -0.04,
  vx: 0, vz: 0,
  fov: 1.02,
};

const game = {
  mode: 'walk',       // walk | focus
  focusIndex: -1,
  hovered: -1,
  tool: 'rotate',     // rotate | draw
  started: false,
  time: 0,          // «дальнее» время: по нему живут мир и ветряк
  proper: 0,        // собственное время наблюдателя
  dilation: 1,      // во сколько раз дальние часы идут быстрее наших
  splash: 99,       // секунд с момента, когда мыли руки
  washed: false,
  wash: { active: false, t: 0, vis: 0 },
  tent: { inside: false, yaw: 0, from: null },
  rocket: { inside: false, shown: '' },
  world: 'earth',     // earth | gamma — под ногами один ландшафт, разные палитры
  zoom: 1,            // приближение вида: во столько раз уже поле зрения
  reduced: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
};

const view = m4(), proj = m4(), vp = m4(), invVP = m4(), model = m4(), tmp = m4();

function camForward() {
  const cp = Math.cos(cam.pitch);
  return [Math.sin(cam.yaw) * cp, Math.sin(cam.pitch), -Math.cos(cam.yaw) * cp];
}

function eyeHeight(x, z) {
  // на полигоне под ногами свой ландшафт; после взрыва нас ещё и роняет
  return groundH(x, z) + 1.66 - (typeof HIT === 'undefined' ? 0 : HIT.down);
}

/* ============================================================
   Отрисовка
   ============================================================ */

let renderScale = 1;      // подстраивается под реальную частоту кадров

function resize() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2) * renderScale;
  const w = Math.max(320, Math.floor(canvas.clientWidth * dpr));
  const h = Math.max(240, Math.floor(canvas.clientHeight * dpr));
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w; canvas.height = h;
  }
}

function drawScene() {
  resize();
  const w = canvas.width, h = canvas.height;
  gl.viewport(0, 0, w, h);

  const onEarth = game.world === 'earth';
  // на полигоне воздух прозрачнее: город в пяти километрах должен быть виден
  const fogK = onEarth ? FOG_K : 0.000115;
  const sh = BLAST.shake;
  const eye = sh > 0.001
    ? [cam.x + Math.sin(game.proper * 47.3) * sh * 0.09,
       cam.y + Math.sin(game.proper * 61.7) * sh * 0.11,
       cam.z + Math.cos(game.proper * 53.1) * sh * 0.09]
    : [cam.x, cam.y, cam.z];
  const f = camForward();

  // Линза и синий сдвиг нужны не всегда: если дыра далеко, за спиной и часы
  // почти не расходятся — рисуем сразу на экран и экономим целый проход.
  const bdx = BH.pos[0] - eye[0], bdy = BH.pos[1] - eye[1], bdz = BH.pos[2] - eye[2];
  const bDist = Math.hypot(bdx, bdy, bdz) || 1;
  const facing = (bdx * f[0] + bdy * f[1] + bdz * f[2]) / bDist;
  // дыра осталась в Неваде: на полигоне ни линзы, ни расхождения часов
  const bhHere = game.world === 'earth';
  const usePost = quasarLens > 0.01
    || (bhHere && (game.dilation > 1.02 || (facing > -0.25 && Math.atan(BH.rs / bDist) > 0.012)));

  if (usePost) {
    sizeFbo(w, h);
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo.fb);
  } else {
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }
  gl.viewport(0, 0, w, h);
  // на Гамме горизонт в семи километрах — ближнюю плоскость отодвигаем,
  // иначе не хватает точности глубины на дальних кварталах
  m4perspective(proj, cam.fov, w / h, onEarth ? 0.08 : 0.30, onEarth ? 900 : 14000);
  m4lookAt(view, eye, [eye[0] + f[0], eye[1] + f[1], eye[2] + f[2]], [0, 1, 0]);
  m4mul(vp, proj, view);
  m4invert(invVP, vp);

  gl.clearColor(HAZE[0], HAZE[1], HAZE[2], 1);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  gl.enable(gl.DEPTH_TEST);
  gl.depthFunc(gl.LEQUAL);
  gl.disable(gl.BLEND);
  gl.disable(gl.CULL_FACE);

  // Выше 650 метров туман и так съел весь ландшафт — экономим на нём кадр.
  const showWorld = ROCKET.alt + ROCKET.cruise < 1500;
  const WT = WORLDS[game.world].ground;

  // — песок
  if (showWorld) {
  const GAS = onEarth ? null : gammaAssets();
  const land = onEarth ? terrain : GAS.terrain;
  gl.useProgram(groundProg.prog);
  attrib(groundProg.a.aPos, land.pos, 3);
  attrib(groundProg.a.aNormal, land.nrm, 3);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, onEarth ? texGround : GAS.soil);
  gl.uniform1i(groundProg.u.uTex, 0);
  gl.uniformMatrix4fv(groundProg.u.uVP, false, vp);
  gl.uniform3fv(groundProg.u.uSun, SUN);
  gl.uniform3fv(groundProg.u.uHaze, HAZE);
  gl.uniform3fv(groundProg.u.uLight, LIGHT);
  gl.uniform3fv(groundProg.u.uAmb, AMB);
  gl.uniform3fv(groundProg.u.uCam, eye);
  gl.uniform1f(groundProg.u.uExtent, onEarth ? GROUND_EXTENT : 26);
  gl.uniform1f(groundProg.u.uTile, onEarth ? 0 : 1);
  gl.uniform3fv(groundProg.u.uGround, WT);
  gl.uniform1f(groundProg.u.uFogK, fogK);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, land.idx);
  gl.drawElements(gl.TRIANGLES, land.count, gl.UNSIGNED_SHORT, 0);

  if (onEarth) {
  // — скалы и камни
  gl.useProgram(solidProg.prog);
  attrib(solidProg.a.aPos, solids.pos, 3);
  attrib(solidProg.a.aNormal, solids.nrm, 3);
  attrib(solidProg.a.aColor, solids.col, 3);
  gl.uniformMatrix4fv(solidProg.u.uVP, false, vp);
  gl.uniformMatrix4fv(solidProg.u.uModel, false, m4identity(tmp));
  gl.uniform3f(solidProg.u.uTint, 1, 1, 1);
  gl.uniform1f(solidProg.u.uFogK, fogK);
  gl.uniform3fv(solidProg.u.uSun, SUN);
  gl.uniform3fv(solidProg.u.uHaze, HAZE);
  gl.uniform3fv(solidProg.u.uLight, LIGHT);
  gl.uniform3fv(solidProg.u.uAmb, AMB);
  gl.uniform3fv(solidProg.u.uCam, eye);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, solids.idx);
  gl.drawElements(gl.TRIANGLES, solids.count, gl.UNSIGNED_SHORT, 0);

  // — колесо ветряка: крутится по «дальнему» времени, поэтому у дыры разгоняется
  m4compose(model, MILL.x, MILL.y - 0.3 + MILL.h, MILL.z, MILL.facing, 0, game.time * 1.15, 1);
  gl.uniformMatrix4fv(solidProg.u.uModel, false, model);
  attrib(solidProg.a.aPos, rotor.pos, 3);
  attrib(solidProg.a.aNormal, rotor.nrm, 3);
  attrib(solidProg.a.aColor, rotor.col, 3);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, rotor.idx);
  gl.drawElements(gl.TRIANGLES, rotor.count, gl.UNSIGNED_SHORT, 0);

  // — ладони: висят в системе камеры, поэтому туман к ним не применяем
  if (game.wash.vis > 0.002) {
    const t = game.wash.t;
    const rub = Math.sin(t * 7.4), rub2 = Math.sin(t * 7.4 + 1.3);
    const drop = -0.62 * (1 - game.wash.vis);
    const camRight = [Math.cos(cam.yaw), 0, Math.sin(cam.yaw)];
    const camUp = [-f[0] * f[1], 1 - f[1] * f[1], -f[2] * f[1]];
    const ul = Math.hypot(camUp[0], camUp[1], camUp[2]) || 1;
    camUp[0] /= ul; camUp[1] /= ul; camUp[2] /= ul;
    // руки отмываются от пыли за те же пять секунд
    const clean = clamp(t / 4.2, 0, 1);
    const tint = 1.18;   // ладони близко к лицу и не должны тонуть в контровом свете
    // грязные руки не темнее, а серее — иначе в контровом свете это просто доски
    gl.uniform3f(solidProg.u.uTint,
      lerp(0.94, 1.06, clean) * tint, lerp(0.90, 1.02, clean) * tint, lerp(0.84, 1.00, clean) * tint);
    gl.uniform1f(solidProg.u.uFogK, 0);
    for (let i = 0; i < 2; i++) {
      const sgn = i ? -1 : 1;
      // смотрим сверху на тыльные стороны кистей: одна трёт другую
      const off = [
        sgn * (0.042 + rub * 0.022),
        -0.104 + drop + sgn * 0.017 + rub2 * 0.008,
        -0.455 - sgn * rub * 0.030,
      ];
      m4viewLocal(model, eye, camRight, camUp, f, off,
        sgn * (0.34 + rub * 0.09),          // кисти почти параллельны, одна над другой
        -cam.pitch - 0.04 + rub2 * 0.06,    // держим горизонтально по миру
        -sgn * (0.22 + rub * 0.08),         // лёгкий разворот ладоней внутрь
        1.14);
      gl.uniformMatrix4fv(solidProg.u.uModel, false, model);
      attrib(solidProg.a.aPos, hands[i].pos, 3);
      attrib(solidProg.a.aNormal, hands[i].nrm, 3);
      attrib(solidProg.a.aColor, hands[i].col, 3);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, hands[i].idx);
      gl.drawElements(gl.TRIANGLES, hands[i].count, gl.UNSIGNED_SHORT, 0);
    }
    gl.uniform3f(solidProg.u.uTint, 1, 1, 1);
    gl.uniform1f(solidProg.u.uFogK, fogK);
  }

  // — палатка: ночью её изнутри подсвечивает фонарь
  const lampWarm = 0.25 + 0.75 * nightAmount;
  gl.uniform3f(solidProg.u.uTint,
    1 + 0.55 * lampWarm * nightAmount, 1 + 0.30 * lampWarm * nightAmount, 1 - 0.05 * nightAmount);
  gl.uniformMatrix4fv(solidProg.u.uModel, false, m4identity(tmp));
  attrib(solidProg.a.aPos, tentMesh.pos, 3);
  attrib(solidProg.a.aNormal, tentMesh.nrm, 3);
  attrib(solidProg.a.aColor, tentMesh.col, 3);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, tentMesh.idx);
  gl.drawElements(gl.TRIANGLES, tentMesh.count, gl.UNSIGNED_SHORT, 0);

  // — кот: дышит и чуть покачивается
  const breath = 1 + 0.018 * Math.sin(game.time * 1.5);
  // кот сидит на подушке и смотрит на вход
  m4compose(model, TENT.cat[0], TENT.cat[1], TENT.cat[2],
    -TENT.yaw + 0.22 + 0.07 * Math.sin(game.time * 0.4), 0, 0, breath);
  gl.uniformMatrix4fv(solidProg.u.uModel, false, model);
  attrib(solidProg.a.aPos, catMesh.pos, 3);
  attrib(solidProg.a.aNormal, catMesh.nrm, 3);
  attrib(solidProg.a.aColor, catMesh.col, 3);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, catMesh.idx);
  gl.drawElements(gl.TRIANGLES, catMesh.count, gl.UNSIGNED_SHORT, 0);
  gl.uniform3f(solidProg.u.uTint, 1, 1, 1);
  catMesh.model = catMesh.model || m4();
  catMesh.model.set(model);

  // — вода в баке
  gl.useProgram(waterProg.prog);
  attrib(waterProg.a.aPos, water.pos, 3);
  gl.uniformMatrix4fv(waterProg.u.uVP, false, vp);
  gl.uniform3fv(waterProg.u.uCam, eye);
  gl.uniform3fv(waterProg.u.uSun, SUN);
  gl.uniform3fv(waterProg.u.uHaze, HAZE);
  gl.uniform3fv(waterProg.u.uLight, LIGHT);
  gl.uniform3fv(waterProg.u.uAmb, AMB);
  gl.uniform2f(waterProg.u.uCenter, TANK.x, TANK.z);
  gl.uniform1f(waterProg.u.uTime, game.time);
  gl.uniform1f(waterProg.u.uSplash, game.splash);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, water.idx);
  gl.drawElements(gl.TRIANGLES, water.count, gl.UNSIGNED_SHORT, 0);

  // — тени под фигурами (умножением)
  const right = [Math.cos(cam.yaw), 0, Math.sin(cam.yaw)];
  const up = [0, 1, 0];
  gl.useProgram(spriteProg.prog);
  gl.uniformMatrix4fv(spriteProg.u.uVP, false, vp);
  gl.uniform3fv(spriteProg.u.uHaze, HAZE);
  gl.uniform3fv(spriteProg.u.uCam, eye);
  gl.uniform3fv(spriteProg.u.uRight, right);
  gl.uniform3fv(spriteProg.u.uUp, up);
  gl.uniform1f(spriteProg.u.uTime, game.time);
  gl.uniform3f(spriteProg.u.uTint, 1, 1, 1);
  const dayLit = [
    0.42 * AMB[0] + 0.62 * LIGHT[0],
    0.42 * AMB[1] + 0.62 * LIGHT[1],
    0.42 * AMB[2] + 0.62 * LIGHT[2],
  ];
  const BUSH_TINT = [0.88 * dayLit[0], 0.86 * dayLit[1], 0.74 * dayLit[2]];

  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  gl.depthMask(false);
  gl.uniform1f(spriteProg.u.uMode, 0);
  gl.uniform1f(spriteProg.u.uAlphaTest, 0.0);
  gl.uniform1f(spriteProg.u.uSway, 0);
  gl.uniform1f(spriteProg.u.uFade, 1);
  gl.bindTexture(gl.TEXTURE_2D, texShadow);
  attrib(spriteProg.a.aCenter, shadows.center, 3);
  attrib(spriteProg.a.aCorner, shadows.corner, 2);
  attrib(spriteProg.a.aUv, shadows.uv, 2);
  attrib(spriteProg.a.aPhase, shadows.phase, 1);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, shadows.idx);
  gl.drawElements(gl.TRIANGLES, shadows.count, gl.UNSIGNED_SHORT, 0);
  gl.depthMask(true);
  gl.disable(gl.BLEND);

  // — полынь
  gl.uniform1f(spriteProg.u.uMode, 1);
  gl.uniform1f(spriteProg.u.uAlphaTest, 0.42);
  gl.uniform1f(spriteProg.u.uSway, game.reduced ? 0.01 : 0.045);
  gl.uniform3fv(spriteProg.u.uTint, BUSH_TINT);
  gl.bindTexture(gl.TEXTURE_2D, texBush);
  attrib(spriteProg.a.aCenter, bushes.center, 3);
  attrib(spriteProg.a.aCorner, bushes.corner, 2);
  attrib(spriteProg.a.aUv, bushes.uv, 2);
  attrib(spriteProg.a.aPhase, bushes.phase, 1);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, bushes.idx);
  gl.drawElements(gl.TRIANGLES, bushes.count, gl.UNSIGNED_SHORT, 0);

  // — ленты
  gl.useProgram(bandProg.prog);
  gl.uniformMatrix4fv(bandProg.u.uVP, false, vp);
  gl.uniform3fv(bandProg.u.uCam, eye);
  gl.uniform3fv(bandProg.u.uSun, SUN);
  gl.uniform3fv(bandProg.u.uHaze, HAZE);
  gl.uniform3fv(bandProg.u.uLight, LIGHT);
  gl.uniform3fv(bandProg.u.uAmb, AMB);
  gl.uniform3fv(bandProg.u.uLine, ACCENT);
  gl.uniform1f(bandProg.u.uR, BAND_R);
  gl.uniform1f(bandProg.u.uW, BAND_W);

  for (const s of SHAPES) {
    const bob = game.reduced ? 0 : 1;
    const t = game.time;
    const py = s.pos[1] + Math.sin(t * 0.62 + s.phase) * 0.085 * bob;
    const tilt = Math.sin(t * 0.41 + s.phase * 1.7) * 0.045 * bob;
    const roll = Math.cos(t * 0.35 + s.phase) * 0.035 * bob;
    const idle = s.focus > 0.5 ? 0 : t * 0.085;

    const fit = lerp(1, s.k === 0 ? 0.66 : 0.58, s.sep);
    m4compose(model, s.pos[0], py, s.pos[2], s.rotY + idle, s.rotX + tilt, roll, s.zoom * fit);
    if (!s.model) s.model = m4();
    s.model.set(model);
    gl.uniformMatrix4fv(bandProg.u.uModel, false, model);
    gl.uniform1f(bandProg.u.uK, s.k);
    gl.uniform1f(bandProg.u.uGap, s.cut * 0.14);
    gl.uniform1f(bandProg.u.uSep, s.sep);
    gl.uniform1f(bandProg.u.uSpread, s.spread);
    gl.uniform1f(bandProg.u.uProgress, s.progress);
    gl.uniform1f(bandProg.u.uLineFade, 1 - s.cut);
    gl.uniform3fv(bandProg.u.uFaceA, s.faceA);
    gl.uniform3fv(bandProg.u.uFaceB, s.faceB);

    attrib(bandProg.a.aU, s.mesh.u, 1);
    attrib(bandProg.a.aS, s.mesh.s, 1);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, s.mesh.idx);

    for (const piece of s.pieces) {
      gl.uniform1f(bandProg.u.uSide, piece.side);
      gl.uniform3fv(bandProg.u.uOffset, piece.offset);
      gl.drawElements(gl.TRIANGLES, s.mesh.count, gl.UNSIGNED_SHORT, 0);
    }
  }
  } else {
    drawGamma(vp, eye, f, fogK);
  }   // мир под ногами

  }   // showWorld

  // — небо рисуем последним: там, где уже лежит геометрия, тест глубины
  //   отбрасывает эти пиксели, и дорогой ночной шейдер по ним не бегает
  gl.useProgram(skyProg.prog);
  gl.depthMask(false);
  attrib(skyProg.a.aPos, quadScreen, 2);
  gl.uniformMatrix4fv(skyProg.u.uInvVP, false, invVP);
  gl.uniform3fv(skyProg.u.uCam, eye);
  gl.uniform3fv(skyProg.u.uSun, SUN);
  gl.uniform3fv(skyProg.u.uHaze, HAZE);
  gl.uniform1f(skyProg.u.uNight, nightAmount);
  gl.uniform1f(skyProg.u.uSpace, spaceAmount);
  gl.uniform1f(skyProg.u.uZoom, quasarZoom);
  gl.uniform1f(skyProg.u.uTime, game.time);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, texMilky);
  gl.uniform1i(skyProg.u.uMilky, 0);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  gl.depthMask(true);


  // — ракета: в режиме невидимости её просто не рисуем
  if (!ROCKET.stealth) {
    gl.useProgram(solidProg.prog);
    gl.uniformMatrix4fv(solidProg.u.uVP, false, vp);
    gl.uniform3fv(solidProg.u.uSun, SUN);
    gl.uniform3fv(solidProg.u.uHaze, HAZE);
    gl.uniform3fv(solidProg.u.uCam, eye);
    gl.uniform3fv(solidProg.u.uLight, LIGHT);
    gl.uniform3fv(solidProg.u.uAmb, AMB);
    gl.uniform3f(solidProg.u.uTint, 1, 1, 1);
    gl.uniform1f(solidProg.u.uFogK, ROCKET.alt > 200 ? 0 : FOG_K);
    gl.uniformMatrix4fv(solidProg.u.uModel, false, ROCKET.model);
    // изнутри рисуем только фонарь, панель и кресло: пол кабины остеклён,
    // иначе взгляд вниз упирается в собственный бак вместо планеты
    const rm = game.rocket.inside ? cockpitMesh : rocketMesh;
    attrib(solidProg.a.aPos, rm.pos, 3);
    attrib(solidProg.a.aNormal, rm.nrm, 3);
    attrib(solidProg.a.aColor, rm.col, 3);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, rm.idx);
    gl.drawElements(gl.TRIANGLES, rm.count, gl.UNSIGNED_SHORT, 0);
  }

  // — ядерное испытание: земля, волна, дым и пламя
  drawBlast(vp, eye, f);

  // — мусор, падающий в дыру: вытянут вдоль радиуса приливными силами
  if (showWorld && onEarth) {
    gl.useProgram(solidProg.prog);
    gl.uniformMatrix4fv(solidProg.u.uVP, false, vp);
    gl.uniform3f(solidProg.u.uTint, 1, 1, 1);
    gl.uniform1f(solidProg.u.uFogK, fogK);
    gl.uniform3fv(solidProg.u.uLight, LIGHT);
    gl.uniform3fv(solidProg.u.uAmb, AMB);
    attrib(solidProg.a.aPos, glowDot.pos, 3);
    attrib(solidProg.a.aNormal, glowDot.nrm, 3);
    gl.disableVertexAttribArray(solidProg.a.aColor);
    gl.vertexAttrib3f(solidProg.a.aColor, 0.42, 0.36, 0.32);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, glowDot.idx);
    for (const d of DEBRIS) {
      gl.uniformMatrix4fv(solidProg.u.uModel, false, debrisMatrix(d, spaceTmp));
      gl.drawElements(gl.TRIANGLES, glowDot.count, gl.UNSIGNED_SHORT, 0);
    }
    gl.enableVertexAttribArray(solidProg.a.aColor);
  }

  // — нормали к средней линии: щетинка по проведённому участку,
  //   яркая стрелка на острие и бледная в точке старта
  if (showWorld && onEarth) {
  gl.useProgram(normalProg.prog);
  gl.uniformMatrix4fv(normalProg.u.uVP, false, vp);
  gl.uniform3fv(normalProg.u.uCam, eye);
  gl.uniform3fv(normalProg.u.uSun, SUN);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

  for (const s of SHAPES) {
    const fade = (1 - s.cut) * (s.progress > 0.001 ? 1 : 0);
    if (fade < 0.02 || !s.model) continue;
    const scale = s.zoom * lerp(1, s.k === 0 ? 0.66 : 0.58, s.sep);

    gl.uniform1f(normalProg.u.uFade, fade);

    // щетинка
    gl.uniformMatrix4fv(normalProg.u.uModel, false, s.model);
    gl.uniform1f(normalProg.u.uProgress, s.progress);
    gl.uniform3f(normalProg.u.uColor, 0.11, 0.52, 0.50);   // след тусклее самих стрелок
    attrib(normalProg.a.aPos, s.hairs.pos, 3);
    attrib(normalProg.a.aNormal, s.hairs.nrm, 3);
    attrib(normalProg.a.aU, s.hairs.us, 1);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, s.hairs.idx);
    gl.drawElements(gl.TRIANGLES, s.hairs.count, gl.UNSIGNED_SHORT, 0);

    // две стрелки поверх
    gl.uniform1f(normalProg.u.uProgress, 2);
    attrib(normalProg.a.aPos, unitArrow.pos, 3);
    attrib(normalProg.a.aNormal, unitArrow.nrm, 3);
    attrib(normalProg.a.aU, unitArrow.us, 1);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, unitArrow.idx);

    for (const a of [
      { u: 0, len: 0.46, rad: 0.055, col: [1.0, 0.48, 0.16] },              // нормаль в точке старта
      { u: s.progress * TAU, len: 0.62, rad: 0.042, col: [0.50, 1.0, 0.94] }, // нормаль на острие
    ]) {
      m4arrow(arrowModel, bandPoint(a.u, 0, s.k, BAND_R), bandNormal(a.u, s.k, BAND_R), a.len, a.rad);
      m4mul(arrowFull, s.model, arrowModel);
      gl.uniformMatrix4fv(normalProg.u.uModel, false, arrowFull);
      gl.uniform3fv(normalProg.u.uColor, a.col);
      gl.drawElements(gl.TRIANGLES, unitArrow.count, gl.UNSIGNED_SHORT, 0);
    }
  }
  // огонёк фонаря и глаза кота — рисуем без освещения
  {
    const flame = 0.55 + 0.45 * nightAmount;
    const pulse = 0.9 + 0.1 * Math.sin(game.time * 6.0);
    gl.uniform1f(normalProg.u.uProgress, 2);
    gl.uniform1f(normalProg.u.uFade, 1);
    attrib(normalProg.a.aPos, glowDot.pos, 3);
    attrib(normalProg.a.aNormal, glowDot.nrm, 3);
    attrib(normalProg.a.aU, glowDot.us, 1);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, glowDot.idx);

    m4compose(arrowModel, TENT.lamp[0], TENT.lamp[1], TENT.lamp[2], 0, 0, 0, 0.055 * pulse);
    gl.uniformMatrix4fv(normalProg.u.uModel, false, arrowModel);
    gl.uniform3f(normalProg.u.uColor, 1.0 * flame, 0.72 * flame, 0.32 * flame);
    gl.drawElements(gl.TRIANGLES, glowDot.count, gl.UNSIGNED_SHORT, 0);

    const eye = 0.32 + 0.68 * nightAmount;
    for (const sx of [-0.045, 0.045]) {
      m4identity(arrowModel);
      arrowModel[0] = arrowModel[5] = arrowModel[10] = 0.017;
      const local = [sx, 0.475, -0.215];
      // положение глаза берём из модельной матрицы кота
      arrowModel[12] = catMesh.model[0] * local[0] + catMesh.model[4] * local[1] + catMesh.model[8] * local[2] + catMesh.model[12];
      arrowModel[13] = catMesh.model[1] * local[0] + catMesh.model[5] * local[1] + catMesh.model[9] * local[2] + catMesh.model[13];
      arrowModel[14] = catMesh.model[2] * local[0] + catMesh.model[6] * local[1] + catMesh.model[10] * local[2] + catMesh.model[14];
      gl.uniformMatrix4fv(normalProg.u.uModel, false, arrowModel);
      gl.uniform3f(normalProg.u.uColor, 0.95 * eye, 0.88 * eye, 0.35 * eye);
      gl.drawElements(gl.TRIANGLES, glowDot.count, gl.UNSIGNED_SHORT, 0);
    }
  }
  gl.disable(gl.BLEND);
  }   // showWorld: наземные стрелки, огни и подписи

  // — дальний план: планета под нами и соседи по системе
  if (planetFade > 0.01 || spaceAmount > 0.01) {
    // Вся сфера прижата к дальней плоскости, поэтому её собственные грани
    // не могут спорить по глубине — отсекаем задние и не пишем глубину.
    gl.enable(gl.CULL_FACE);
    gl.cullFace(gl.BACK);
    gl.depthMask(false);
    gl.useProgram(planetProg.prog);
    gl.uniformMatrix4fv(planetProg.u.uVP, false, vp);
    gl.uniform3fv(planetProg.u.uSun, SUN);
    attrib(planetProg.a.aPos, sphereMesh.pos, 3);
    attrib(planetProg.a.aUv, sphereMesh.uv, 2);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, sphereMesh.idx);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, onEarth ? texPlanet : texGamma);
    gl.uniform1i(planetProg.u.uTex, 0);

    const home = onEarth ? PLANET_HOME : GAMMA.home;
    const RP = onEarth ? PLANET_R : GAMMA.R;   // радиус мира под ногами
    const D = 600;          // условное удаление дальнего плана

    // соседи: висят в фиксированных направлениях
    gl.uniform1f(planetProg.u.uMode, 1);
    m4identity(spaceRot);
    for (const n of NEIGHBOURS) {
      gl.uniform1f(planetProg.u.uFade, spaceAmount);
      gl.uniform1f(planetProg.u.uNear, 0);
      gl.uniform1f(planetProg.u.uCloud, 0);
      gl.uniform1f(planetProg.u.uLimb, 0);
      gl.uniform3f(planetProg.u.uRim, n.dir[0], n.dir[1], n.dir[2]);
      gl.uniform3f(planetProg.u.uCenter, eye[0] + n.dir[0] * D, eye[1] + n.dir[1] * D, eye[2] + n.dir[2] * D);
      gl.uniform1f(planetProg.u.uRadius, D * n.ang);
      gl.uniform3fv(planetProg.u.uColor, n.col);
      m4compose(spaceRot, 0, 0, 0, game.time * 0.02, 0.3, 0, 1);
      gl.uniformMatrix4fv(planetProg.u.uRot, false, spaceRot);
      gl.drawElements(gl.TRIANGLES, sphereMesh.count, gl.UNSIGNED_SHORT, 0);
    }
    // родная планета крупнее и рисуется последней, перекрывая соседей.
    // Радиус сферы фиксирован, а её центр отодвигается так, чтобы угловой
    // размер отвечал высоте — иначе на малой высоте сфера накрыла бы камеру.
    // расстояние до центра планеты растёт и при подъёме, и на крейсере —
    // отсюда честное убывание углового размера
    // Угловой радиус честный: asin(R / (R + высота)) — отсюда убывание по
    // обратному закону при отлёте. Сам шар не строим в натуральную величину:
    // держим его ближнюю точку на постоянном отступе GAP под кабиной и
    // подбираем радиус под нужный угол. Иначе на малой высоте поверхность
    // подходит к камере вплотную и вместо планеты видно белое пятно.
    const sinA = clamp(RP / (RP + Math.max(ROCKET.alt + ROCKET.cruise, 1)), 0, 0.995);
    const GAP = 4000;
    const dc = GAP / (1 - sinA);
    const PR = dc * sinA;
    gl.uniform1f(planetProg.u.uMode, 0);
    gl.uniform1f(planetProg.u.uFade, planetFade);
    gl.uniform1f(planetProg.u.uNear, smoothstep(0.55, 0.93, sinA));
    gl.uniform1f(planetProg.u.uCloud, 1);
    gl.uniform1f(planetProg.u.uLimb, sinA);
    gl.uniform1f(planetProg.u.uTime, game.time);
    gl.uniform3f(planetProg.u.uRim, 0, 1, 0);      // камера строго над центром
    gl.uniform3f(planetProg.u.uCenter, eye[0], eye[1] - dc, eye[2]);
    gl.uniform1f(planetProg.u.uRadius, PR);
    // «дом» держим ровно под кораблём: под нами всегда та же площадка
    m4align(spaceRot, home, [0, -1, 0]);
    gl.uniformMatrix4fv(planetProg.u.uRot, false, spaceRot);
    gl.uniform1f(planetProg.u.uCloud, onEarth ? 1 : 0.35);
    gl.drawElements(gl.TRIANGLES, sphereMesh.count, gl.UNSIGNED_SHORT, 0);

    /* — планета назначения: висит в своей стороне неба и растёт при подлёте.
         Тот же приём: шар отодвинут так, чтобы ближняя точка была в GAP. */
    const target = onEarth ? GAMMA : { R: PLANET_R, home: PLANET_HOME };
    const tdir = onEarth ? GAMMA.dir : [-GAMMA.dir[0], -GAMMA.dir[1], -GAMMA.dir[2]];
    const tsin = clamp(Math.sin(gammaAng), 0, 0.995);
    if (tsin > 1e-4) {
      const tdc = GAP / (1 - tsin), tr = tdc * tsin;
      gl.uniform1f(planetProg.u.uFade, spaceAmount);
      gl.uniform1f(planetProg.u.uNear, smoothstep(0.55, 0.93, tsin));
      gl.uniform1f(planetProg.u.uLimb, tsin);
      gl.uniform1f(planetProg.u.uCloud, onEarth ? 0.35 : 1);
      gl.uniform3f(planetProg.u.uRim, -tdir[0], -tdir[1], -tdir[2]);
      gl.uniform3f(planetProg.u.uCenter, eye[0] + tdir[0] * tdc, eye[1] + tdir[1] * tdc, eye[2] + tdir[2] * tdc);
      gl.uniform1f(planetProg.u.uRadius, tr);
      gl.bindTexture(gl.TEXTURE_2D, onEarth ? texGamma : texPlanet);
      m4align(spaceRot, target.home, [-tdir[0], -tdir[1], -tdir[2]]);
      gl.uniformMatrix4fv(planetProg.u.uRot, false, spaceRot);
      gl.drawElements(gl.TRIANGLES, sphereMesh.count, gl.UNSIGNED_SHORT, 0);
    }

    gl.disable(gl.CULL_FACE);
    gl.depthMask(true);
  }

  // — рождение и аннигиляция пар у горизонта
  if (PAIRS.n > 0) {
    gl.useProgram(pointProg.prog);
    gl.uniformMatrix4fv(pointProg.u.uVP, false, vp);
    gl.uniform3fv(pointProg.u.uCam, eye);
    gl.uniform1f(pointProg.u.uScale, 26 * (canvas.height / 700));
    attrib(pointProg.a.aPos, PAIRS.buf, 3);
    attrib(pointProg.a.aColor, PAIRS.cbuf, 4);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
    gl.depthMask(false);
    gl.drawArrays(gl.POINTS, 0, PAIRS.n);
    gl.depthMask(true);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  }

  // — подписи фигур: только там, где сами фигуры
  if (onEarth) {
  gl.useProgram(spriteProg.prog);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  gl.depthMask(false);
  gl.uniform1f(spriteProg.u.uMode, 2);
  gl.uniform3f(spriteProg.u.uTint, 1, 1, 1);
  gl.uniform1f(spriteProg.u.uAlphaTest, 0.01);
  gl.uniform1f(spriteProg.u.uSway, 0);
  const camRight = [Math.cos(cam.yaw), 0, Math.sin(cam.yaw)];
  const camUp = [0, 1, 0];
  gl.uniform3fv(spriteProg.u.uRight, camRight);
  gl.uniform3fv(spriteProg.u.uUp, camUp);
  SHAPES.forEach((s, i) => {
    if (!showWorld) return;
    const fade = (1 - s.focus) * (game.focusIndex < 0 || game.focusIndex === i ? 1 : 0.25);
    if (fade < 0.02) return;
    gl.uniform1f(spriteProg.u.uFade, fade);
    gl.bindTexture(gl.TEXTURE_2D, labels[i].tex);
    const q = labels[i].quad;
    attrib(spriteProg.a.aCenter, q.center, 3);
    attrib(spriteProg.a.aCorner, q.corner, 2);
    attrib(spriteProg.a.aUv, q.uv, 2);
    attrib(spriteProg.a.aPhase, q.phase, 1);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, q.idx);
    gl.drawElements(gl.TRIANGLES, q.count, gl.UNSIGNED_SHORT, 0);
  });
  gl.depthMask(true);
  gl.disable(gl.BLEND);

  // ---- пост-обработка: линза чёрной дыры ----
  }   // onEarth: подписи

  if (!usePost) return;
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  gl.viewport(0, 0, w, h);
  gl.disable(gl.DEPTH_TEST);
  gl.useProgram(postProg.prog);
  attrib(postProg.a.aPos, quadScreen, 2);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, fbo.tex);
  gl.uniform1i(postProg.u.uScene, 0);

  // Ближе 200 000 км линзой работает квазар, иначе — наземная дыра.
  let lx, ly, lz, lensVisible, shadow;
  if (quasarLens > 0.01) {
    lx = eye[0] + SUN[0] * 50; ly = eye[1] + SUN[1] * 50; lz = eye[2] + SUN[2] * 50;
    const range = Math.max(quasarRange(), QUASAR_R * 1.05);
    shadow = Math.asin(clamp(QUASAR_R * 0.38 / range, 0, 0.99)) / (cam.fov * 0.5) * 0.5;
    lensVisible = quasarLens;
  } else {
    lx = BH.pos[0]; ly = BH.pos[1]; lz = BH.pos[2];
    shadow = Math.atan(BH.rs / Math.max(bDist, BH.rs * 1.2)) / (cam.fov * 0.5) * 0.5;
    lensVisible = bhHere ? 1 : 0;
  }
  const bx = vp[0] * lx + vp[4] * ly + vp[8] * lz + vp[12];
  const by = vp[1] * lx + vp[5] * ly + vp[9] * lz + vp[13];
  const bw = vp[3] * lx + vp[7] * ly + vp[11] * lz + vp[15];
  const visible = bw > 0.05 ? lensVisible : 0;
  gl.uniform1f(postProg.u.uAspect, w / h);
  gl.uniform2f(postProg.u.uBH, visible ? bx / bw * 0.5 + 0.5 : -5, visible ? by / bw * 0.5 + 0.5 : -5);
  gl.uniform1f(postProg.u.uShadow, shadow);
  gl.uniform1f(postProg.u.uVisible, visible);
  gl.uniform1f(postProg.u.uDil, game.dilation);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  gl.enable(gl.DEPTH_TEST);
}
