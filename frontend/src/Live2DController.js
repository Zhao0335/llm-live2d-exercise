/**
 * Live2DController
 * ----------------
 * 把 pixi-live2d-display(-lipsyncpatch) 的初始化和操作封装起来，
 * 对外提供干净的接口：speak / setExpression / playMotion / stop。
 *
 * 不直接依赖 React/Vue。要嵌入到任何前端框架里，只要拿到一个 <canvas> 即可。
 *
 * 加载顺序很重要：
 *   1. live2dcubismcore.min.js  （Cubism 4 core，在 index.html 用 <script> 引入）
 *   2. live2d.min.js            （Cubism 2.1 老 runtime，可选）
 *   3. pixi.js                  （v7.x）
 *   4. pixi-live2d-display 的 lipsyncpatch fork
 *
 * 这里假设前 4 步都已经在 index.html 里完成，window.PIXI 和 window.PIXI.live2d 可用。
 */

const { PIXI } = window;
const Live2DModel = window.PIXI?.live2d?.Live2DModel;

if (!Live2DModel) {
  console.warn(
    '[Live2DController] PIXI.live2d.Live2DModel not found. ' +
    'Did you include the lipsyncpatch script in index.html?',
  );
}

export class Live2DController {
  /**
   * @param {HTMLCanvasElement} canvas
   */
  constructor(canvas) {
    this.canvas = canvas;
    this.app = null;
    this.model = null;
    this._defaultExpression = null;
    this._expressionResetTimer = null;
    this._currentAudio = null; // 当前正在 speak 的占位
  }

  /**
   * @param {string} modelUrl  指向 .model3.json (Cubism 4) 或 .model.json (2.1)
   * @param {{ scale?: number, x?: number, y?: number }} [opts]
   */
  async load(modelUrl, opts = {}) {
    this.app = new PIXI.Application({
      view: this.canvas,
      autoStart: true,
      resizeTo: this.canvas.parentElement || window,
      backgroundAlpha: 0,
      antialias: true,
    });

    const model = await Live2DModel.from(modelUrl, { autoInteract: false });
    this.model = model;
    this.app.stage.addChild(model);

    this._fit(opts);

    // 记下当前默认表情（用 null 代表"无 expression"）
    this._defaultExpression = null;

    return model;
  }

  _fit(opts) {
    if (!this.model || !this.app) return;
    const parent = this.canvas.parentElement;
    const w = parent?.clientWidth || this.app.view.width;
    const h = parent?.clientHeight || this.app.view.height;

    const scale =
      opts.scale ?? Math.min(w / this.model.width, h / this.model.height) * 0.9;
    this.model.scale.set(scale);
    this.model.x = opts.x ?? (w - this.model.width) / 2;
    this.model.y = opts.y ?? (h - this.model.height) / 2;
  }

  resize() {
    this._fit({});
  }

  /**
   * 用 lipsyncpatch 的 model.speak() 播放音频并自动嘴型同步。
   * 返回一个 Promise，在音频播放结束（或被 stop）后 resolve。
   * @param {string} url
   * @param {{ volume?: number, expression?: string|number, onStart?: () => void }} [opts]
   */
  speak(url, opts = {}) {
    if (!this.model) return Promise.resolve();
    return new Promise((resolve) => {
      const onFinish = () => {
        console.log('[Live2DController] audio finished');
        resolve();
      };
      this._currentAudio = url;
      // 立即执行 onStart 回调（因为库不支持 onStart）
      if (opts.onStart) {
        console.log('[Live2DController] calling onStart immediately');
        opts.onStart();
      }
      try {
        this.model.speak(url, {
          volume: opts.volume ?? 1.0,
          expression: opts.expression,
          resetExpression: false, // 表情寿命由 setExpression 自己控制
          crossOrigin: 'anonymous',
          onFinish,
          onError: (err) => {
            console.warn('[Live2DController] speak error', err);
            resolve();
          },
        });
      } catch (e) {
        console.warn('[Live2DController] speak exception', e);
        resolve();
      }
    });
  }

  /**
   * 立即停止当前正在 speak 的音频（如果有），让嘴巴回到闭合。
   */
  stopSpeaking() {
    if (!this.model) return;
    try {
      // lipsyncpatch 提供 stopSpeaking()
      if (typeof this.model.stopSpeaking === 'function') {
        this.model.stopSpeaking();
      }
    } catch (e) {
      // 忽略
    }
    this._currentAudio = null;
  }

  /**
   * @param {string} name 表情名（model3.json 里 expression 的 name）
   * @param {number} [holdMs] 多久后回到默认表情；0 = 永久保持
   */
  setExpression(name, holdMs = 3000) {
    if (!this.model) return;
    try {
      this.model.expression(name);
    } catch (e) {
      console.warn('[Live2DController] expression not found', name);
      return;
    }
    if (this._expressionResetTimer) {
      clearTimeout(this._expressionResetTimer);
      this._expressionResetTimer = null;
    }
    if (holdMs > 0) {
      this._expressionResetTimer = setTimeout(() => {
        if (this._defaultExpression) {
          try {
            this.model.expression(this._defaultExpression);
          } catch (_) { /* noop */ }
        } else {
          // 没有默认表情时，重置到 null（库会自动回到 base）
          try {
            this.model.expression();
          } catch (_) { /* noop */ }
        }
      }, holdMs);
    }
  }

  /**
   * @param {string} group  motion group 名
   * @param {number|null} [index] 可指定第几个；null = 该组随机
   * @param {number} [priority] 1=idle, 2=normal, 3=force
   */
  playMotion(group, index = null, priority = 2) {
    if (!this.model) return;
    try {
      this.model.motion(group, index ?? undefined, priority);
    } catch (e) {
      console.warn('[Live2DController] motion failed', group, e);
    }
  }

  destroy() {
    if (this._expressionResetTimer) clearTimeout(this._expressionResetTimer);
    this.stopSpeaking();
    if (this.app) {
      this.app.destroy(true, { children: true });
      this.app = null;
      this.model = null;
    }
  }
}
