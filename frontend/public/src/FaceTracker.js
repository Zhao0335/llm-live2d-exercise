/**
 * FaceTracker - 眼球跟踪器
 *
 * 优先使用 MediaPipe FaceMesh 做虹膜追踪（需要在 index.html 里加载 CDN 脚本）；
 * 如果摄像头不可用或 MediaPipe 未加载，自动回退到鼠标跟踪。
 *
 * 对外 API 不变：detectFace() 返回 {x, y}（0~1 范围）。
 */
export class FaceTracker {
  constructor() {
    this.video = null;
    this.faceMesh = null;
    this.camera = null;
    this.isRunning = false;
    this.mode = 'mouse'; // 'mouse' | 'mediapipe'

    // 当前目标位置（0~1）
    this.lastFacePosition = { x: 0.5, y: 0.5 };
    // 平滑后位置
    this.smoothedPosition = { x: 0.5, y: 0.5 };
  }

  async init() {
    // 创建隐藏 video 元素（MediaPipe 需要）
    this.video = document.createElement('video');
    this.video.setAttribute('playsinline', '');
    this.video.style.cssText = 'position:fixed;display:none;';
    document.body.appendChild(this.video);

    // 如果 MediaPipe 已通过 CDN 加载，尝试初始化
    if (window.FaceMesh && window.Camera) {
      try {
        await this._initMediaPipe();
        this.mode = 'mediapipe';
        console.log('[FaceTracker] MediaPipe 虹膜追踪已启用');
        return true;
      } catch (e) {
        console.warn('[FaceTracker] MediaPipe 初始化失败，回退到鼠标模式:', e);
      }
    } else {
      console.log('[FaceTracker] MediaPipe 未加载，使用鼠标跟踪模式');
    }

    // 回退：鼠标模式
    this.mode = 'mouse';
    return true;
  }

  async _initMediaPipe() {
    this.faceMesh = new window.FaceMesh({
      locateFile: (file) =>
        `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}`,
    });

    this.faceMesh.setOptions({
      maxNumFaces: 3,
      // refineLandmarks: true 才能拿到虹膜关键点 468/473
      refineLandmarks: true,
      minDetectionConfidence: 0.5,
      minTrackingConfidence: 0.5,
    });

    this.faceMesh.onResults((results) => this._onResults(results));

    // Camera 工具负责打开摄像头并循环发帧给 FaceMesh
    this.camera = new window.Camera(this.video, {
      onFrame: async () => {
        if (this.isRunning && this.faceMesh) {
          await this.faceMesh.send({ image: this.video });
        }
      },
      width: 320,
      height: 240,
    });

    // 测试是否能成功启动（会弹摄像头权限）
    await this.camera.start();
  }

  _onResults(results) {
    if (!results.multiFaceLandmarks || results.multiFaceLandmarks.length === 0) {
      // 没有检测到人脸，位置保持不变（不跳变）
      return;
    }

    // 选最近的脸（边界框面积最大的）
    const face = this._selectNearestFace(results.multiFaceLandmarks);
    if (!face) return;

    const pos = this._calcIrisPosition(face);
    if (pos) {
      this.lastFacePosition = pos;
    }
  }

  _selectNearestFace(faces) {
    let maxArea = 0;
    let nearest = null;
    for (const face of faces) {
      const xs = face.map((p) => p.x);
      const ys = face.map((p) => p.y);
      const w = Math.max(...xs) - Math.min(...xs);
      const h = Math.max(...ys) - Math.min(...ys);
      const area = w * h;
      if (area > maxArea) {
        maxArea = area;
        nearest = face;
      }
    }
    return nearest;
  }

  _calcIrisPosition(landmarks) {
    // 需要 refineLandmarks:true 才有 468/473 虹膜中心
    if (!landmarks[468] || !landmarks[473]) return null;

    // 左眼：虹膜 468，眼角 33（内）和 133（外）
    const lIris = landmarks[468];
    const lInner = landmarks[33];
    const lOuter = landmarks[133];
    const lWidth = Math.abs(lOuter.x - lInner.x);
    if (lWidth < 0.001) return null;
    const lX = (lIris.x - lInner.x) / lWidth; // 0~1

    // 右眼：虹膜 473，眼角 362（内）和 263（外）
    const rIris = landmarks[473];
    const rInner = landmarks[362];
    const rOuter = landmarks[263];
    const rWidth = Math.abs(rOuter.x - rInner.x);
    if (rWidth < 0.001) return null;
    const rX = (rIris.x - rInner.x) / rWidth; // 0~1

    // 两眼平均，X 方向不反转（摄像头坐标与屏幕坐标一致）
    const avgX = (lX + rX) / 2;
    const avgY = (lIris.y + rIris.y) / 2;

    return {
      x: Math.max(0, Math.min(1, avgX)),
      y: Math.max(0, Math.min(1, avgY)),
    };
  }

  // 鼠标模式下由外部调用，更新目标位置
  updatePosition(x, y) {
    this.lastFacePosition = { x, y };
  }

  // Live2DController 每帧调用，返回平滑后的位置
  async detectFace() {
    if (!this.isRunning) return this.smoothedPosition;

    const alpha = 0.15;
    this.smoothedPosition.x +=
      (this.lastFacePosition.x - this.smoothedPosition.x) * alpha;
    this.smoothedPosition.y +=
      (this.lastFacePosition.y - this.smoothedPosition.y) * alpha;

    return { ...this.smoothedPosition };
  }

  start() {
    this.isRunning = true;
    // MediaPipe 模式下 camera 已在 init 时 start，无需再次启动
  }

  stop() {
    this.isRunning = false;
  }

  destroy() {
    this.stop();
    if (this.camera) {
      try { this.camera.stop(); } catch (_) {}
      this.camera = null;
    }
    if (this.faceMesh) {
      try { this.faceMesh.close(); } catch (_) {}
      this.faceMesh = null;
    }
    if (this.video) {
      this.video.srcObject?.getTracks().forEach((t) => t.stop());
      this.video.remove();
      this.video = null;
    }
  }
}
