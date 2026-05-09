// llm-live2d 前端入口
// 把 Live2DController + ActionClient 串起来，提供最小 UI。

import { Live2DController } from './src/Live2DController.js';
import { ActionClient } from './src/ActionClient.js';
import { FaceTracker } from './src/FaceTracker.js';

// ===== 配置 =====
// 通过 URL query 可覆写，方便 demo：
//   index.html?model=/models/foo/foo.model3.json&ws=ws://localhost:8000/ws
const params = new URLSearchParams(location.search);
const CONFIG = {
  modelUrl:
    params.get('model') ||
    // Shizuku 模型 - 支持 4 个表情 (f01, f02, f03, f04)
    'https://cdn.jsdelivr.net/gh/guansss/pixi-live2d-display/test/assets/shizuku/shizuku.model.json',
  wsUrl: params.get('ws') || `ws://${location.hostname || 'localhost'}:8000/ws`,
};

// ===== DOM =====
const $ = (id) => document.getElementById(id);
const canvas = $('stage');
const input = $('input');
const sendBtn = $('send');
const interruptBtn = $('interrupt');
const eyeTrackingBtn = $('eyeTracking'); // 眼球跟踪按钮
const statusEl = $('status');
const subtitleEl = $('subtitle');
const thinkingEl = $('thinking');
const debugToggle = $('debugToggle');
const debugContent = $('debugContent');
const debugText = $('debugText');
const debugPanel = document.querySelector('.debug-panel');

// ===== 调试面板 =====
debugToggle.addEventListener('click', () => {
  const isHidden = debugContent.hidden;
  debugContent.hidden = !isHidden;
  debugPanel.classList.toggle('expanded', isHidden);
});

// ===== 启动 =====
async function main() {
  const live2d = new Live2DController(canvas);
  try {
    await live2d.load(CONFIG.modelUrl);
  } catch (e) {
    console.error('Failed to load Live2D model', e);
    statusEl.textContent = '模型加载失败';
    statusEl.dataset.state = 'closed';
    return;
  }

  window.addEventListener('resize', () => live2d.resize());

  // 初始化人脸跟踪
  let faceTracker = null;
  let eyeTrackingEnabled = false;

  const initFaceTracker = async () => {
    if (!faceTracker) {
      faceTracker = new FaceTracker();
      const success = await faceTracker.init();
      if (!success) {
        alert('无法访问摄像头，请检查权限设置');
        return false;
      }
    }
    return true;
  };

  // 眼球跟踪开关
  if (eyeTrackingBtn) {
    eyeTrackingBtn.addEventListener('click', async () => {
      if (!eyeTrackingEnabled) {
        const success = await initFaceTracker();
        if (success) {
          faceTracker.start();
          live2d.startEyeTracking(faceTracker);
          eyeTrackingEnabled = true;
          eyeTrackingBtn.textContent = '👁️ 跟踪中';
          eyeTrackingBtn.classList.add('active');

          // 添加鼠标跟踪（默认模式）
          document.addEventListener('mousemove', (e) => {
            if (faceTracker && eyeTrackingEnabled) {
              const x = e.clientX / window.innerWidth;
              const y = e.clientY / window.innerHeight;
              faceTracker.updatePosition(x, y);
            }
          });
        }
      } else {
        faceTracker.stop();
        live2d.stopEyeTracking();
        eyeTrackingEnabled = false;
        eyeTrackingBtn.textContent = '👁️ 眼球跟踪';
        eyeTrackingBtn.classList.remove('active');
      }
    });
  }

  const client = new ActionClient({
    url: CONFIG.wsUrl,
    live2d,
    onSay: (text) => {
      // 字幕：每句替换显示
      subtitleEl.textContent = text;
    },
    onThinking: (text) => {
      thinkingEl.hidden = false;
      thinkingEl.textContent = `💭 ${text}`;
      setTimeout(() => {
        thinkingEl.hidden = true;
      }, 6000);
    },
    onTurnStart: () => {
      subtitleEl.textContent = '';
    },
    onTurnEnd: (_turnId, rawText) => {
      // 显示原始 LLM 返回
      if (rawText) {
        debugText.textContent = rawText;
      }
      // 维持最后一句字幕一会儿，再清空
      setTimeout(() => {
        subtitleEl.textContent = '';
      }, 2500);
    },
    onError: (msg) => {
      console.error('[error]', msg);
    },
    onConnectionChange: (s) => {
      statusEl.dataset.state = s;
      statusEl.textContent =
        s === 'open' ? '已连接' : s === 'closed' ? '已断开' : '连接中…';
    },
  });

  // 发送
  const submit = () => {
    const text = input.value.trim();
    if (!text) return;
    client.send(text);
    input.value = '';
    autoSize();
  };
  sendBtn.addEventListener('click', submit);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  });
  input.addEventListener('input', autoSize);
  function autoSize() {
    input.style.height = 'auto';
    input.style.height = Math.min(160, input.scrollHeight) + 'px';
  }

  // 中断
  interruptBtn.addEventListener('click', () => client.interrupt());
}

main();
