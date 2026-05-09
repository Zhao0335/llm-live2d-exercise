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

    // 眼球跟踪相关
    this.faceTracker = null;
    this._eyeTrackingEnabled = false;
    this._eyeTrackingAnimationId = null;
    this._currentEyeX = 0;
    this._currentEyeY = 0;
    this._targetEyeX = 0;
    this._targetEyeY = 0;
    this._lastBlinkTime = Date.now();
    this._nextBlinkInterval = 3000 + Math.random() * 2000; // 3-5秒
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
        resolve();
      };
      this._currentAudio = url;
      // 立即执行 onStart 回调（因为库不支持 onStart）
      if (opts.onStart) {
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
            resolve();
          },
        });
      } catch (e) {
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
      // 忽略动作错误
    }
  }

  destroy() {
    this.stopEyeTracking();
    if (this._expressionResetTimer) clearTimeout(this._expressionResetTimer);
    this.stopSpeaking();
    if (this.app) {
      this.app.destroy(true, { children: true });
      this.app = null;
      this.model = null;
    }
  }

  /**
   * 启动眼球跟踪
   * @param {import('./FaceTracker').FaceTracker} faceTracker
   */
  startEyeTracking(faceTracker) {
    if (this._eyeTrackingEnabled) return;

    this.faceTracker = faceTracker;
    this._eyeTrackingEnabled = true;

    this._updateEyeTracking();
  }

  stopEyeTracking() {
    this._eyeTrackingEnabled = false;
    if (this._eyeTrackingAnimationId) {
      cancelAnimationFrame(this._eyeTrackingAnimationId);
      this._eyeTrackingAnimationId = null;
    }
  }

  async _updateEyeTracking() {
    if (!this._eyeTrackingEnabled || !this.model) return;

    try {
      // 获取人脸位置
      let facePos = { x: 0.5, y: 0.5 };
      if (this.faceTracker) {
        facePos = await this.faceTracker.detectFace();
      }

      // 将人脸位置转换为眼球参数 (-1 到 1)
      // 人脸在左边 -> 眼球看左边 (x = -1)
      // 人脸在右边 -> 眼球看右边 (x = 1)
      this._targetEyeX = (facePos.x - 0.5) * 2;
      this._targetEyeY = (facePos.y - 0.5) * 2;

      // 添加随机微动（模拟自然眼动）
      const microMovement = 0.02;
      this._targetEyeX += (Math.random() - 0.5) * microMovement;
      this._targetEyeY += (Math.random() - 0.5) * microMovement;

      // 限制范围
      this._targetEyeX = Math.max(-1, Math.min(1, this._targetEyeX));
      this._targetEyeY = Math.max(-1, Math.min(1, this._targetEyeY));

      // 平滑过渡
      const smoothFactor = 0.08;
      this._currentEyeX += (this._targetEyeX - this._currentEyeX) * smoothFactor;
      this._currentEyeY += (this._targetEyeY - this._currentEyeY) * smoothFactor;

      // 设置眼球参数
      this._setEyeParameters(this._currentEyeX, this._currentEyeY);

      // 自然眨眼
      this._handleBlinking();
    } catch (e) {
      // 忽略错误
    }

    // 下一帧继续
    this._eyeTrackingAnimationId = requestAnimationFrame(() => this._updateEyeTracking());
  }

  _setEyeParameters(x, y) {
    if (!this.model || !this.model.internalModel) return;

    const coreModel = this.model.internalModel.coreModel;
    if (!coreModel) return;

    try {
      // 尝试设置眼球参数（不同模型的参数名可能不同）
      // Cubism 2.1 模型
      if (coreModel.getParameterIndex) {
        const eyeXIndex = coreModel.getParameterIndex('ParamEyeBallX');
        const eyeYIndex = coreModel.getParameterIndex('ParamEyeBallY');
        if (eyeXIndex >= 0) coreModel.setParameterValueByIndex(eyeXIndex, x);
        if (eyeYIndex >= 0) coreModel.setParameterValueByIndex(eyeYIndex, y);
      }
      // Cubism 4 模型
      else if (coreModel.setParameterValue) {
        coreModel.setParameterValue('ParamEyeBallX', x);
        coreModel.setParameterValue('ParamEyeBallY', y);
      }
      else {
        // 使用 focus() 方法作为备选
        const canvas = this.canvas;
        const rect = canvas.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const focusX = centerX + x * 200;
        const focusY = centerY + y * 200;
        this.model.focus(focusX, focusY);
      }
    } catch (e) {
      // 忽略参数设置错误
    }
  }

  _handleBlinking() {
    const now = Date.now();

    // 检查是否该眨眼了
    if (now - this._lastBlinkTime > this._nextBlinkInterval) {
      this._blink();
      this._lastBlinkTime = now;
      this._nextBlinkInterval = 3000 + Math.random() * 2000; // 3-5秒后下次眨眼
    }
  }

  _blink() {
    if (!this.model) return;

    try {
      // 触发眨眼（通过设置眼睛参数）
      const coreModel = this.model.internalModel?.coreModel;
      if (!coreModel) return;

      // 眨眼动画：闭眼 -> 开眼
      let blinkPhase = 0;
      const blinkDuration = 150; // 眨眼持续时间（毫秒）
      const startTime = Date.now();

      const blinkAnimation = () => {
        const elapsed = Date.now() - startTime;
        const progress = Math.min(1, elapsed / blinkDuration);

        // 眨眼曲线：0 -> 1 -> 0
        blinkPhase = progress < 0.5
          ? progress * 2  // 闭眼
          : 2 - progress * 2;  // 开眼

        // 设置眼睛开合度
        const eyeOpen = 1 - blinkPhase;
        try {
          if (coreModel.setParameterValue) {
            coreModel.setParameterValue('ParamEyeLOpen', eyeOpen);
            coreModel.setParameterValue('ParamEyeROpen', eyeOpen);
          }
        } catch (e) {
          // 忽略
        }

        if (progress < 1) {
          requestAnimationFrame(blinkAnimation);
        }
      };

      blinkAnimation();
    } catch (e) {
      // 忽略眨眼错误
    }
  }
}
