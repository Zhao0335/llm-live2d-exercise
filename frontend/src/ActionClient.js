/**
 * ActionClient
 * ------------
 * 管理与后端的 WebSocket 连接，把进来的 Action 串行喂给 Live2DController。
 *
 * 关键约束：必须按顺序执行 say + audio。
 * 如果同一时刻收到多个 audio Action，前一个还没播完就播下一个，会发生：
 *   - 嘴部参数被两个音频源同时驱动 → 抖动
 *   - 文字字幕错乱
 * 所以用一个内部 promise 链，保证 audio 是严格串行的。
 *
 * 表情/动作不进串行队列：它们应该立即生效，跟当前正在说的话叠加。
 */

export class ActionClient {
  /**
   * @param {{
   *   url: string,
   *   live2d: import('./Live2DController').Live2DController,
   *   onSay?: (text: string) => void,
   *   onThinking?: (text: string) => void,
   *   onTurnStart?: (turnId: string) => void,
   *   onTurnEnd?: (turnId: string) => void,
   *   onError?: (msg: string) => void,
   *   onConnectionChange?: (state: 'open'|'closed'|'connecting') => void,
   *   audioBaseUrl?: string,   // 后端 /audio/* 的基础地址。默认基于 ws url 推断
   * }} opts
   */
  constructor(opts) {
    this.opts = opts;
    this.ws = null;
    this.audioBase =
      opts.audioBaseUrl ?? this._deriveAudioBase(opts.url);

    this._currentTurnId = null;
    // 每个 turn 一个独立的串行链，被 stop 后立即作废
    this._sayChain = Promise.resolve();
    this._sayChainTurnId = null;

    this._setState('connecting');
    this._connect();
  }

  _deriveAudioBase(wsUrl) {
    try {
      const u = new URL(wsUrl);
      const proto = u.protocol === 'wss:' ? 'https:' : 'http:';
      return `${proto}//${u.host}`;
    } catch {
      return '';
    }
  }

  _setState(s) {
    this._connState = s;
    this.opts.onConnectionChange?.(s);
  }

  _connect() {
    const ws = new WebSocket(this.opts.url);
    this.ws = ws;
    ws.onopen = () => this._setState('open');
    ws.onclose = () => {
      this._setState('closed');
      this.opts.live2d.stopSpeaking();
    };
    ws.onerror = (e) => {
      console.error('[ActionClient] ws error', e);
    };
    ws.onmessage = (ev) => {
      let action;
      try {
        action = JSON.parse(ev.data);
      } catch {
        return;
      }
      this._handleAction(action);
    };
  }

  // ------------- 出站 -------------

  send(text) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.opts.onError?.('Not connected');
      return;
    }
    this.ws.send(JSON.stringify({ type: 'user_message', text }));
  }

  interrupt() {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(
      JSON.stringify({
        type: 'interrupt',
        turn_id: this._currentTurnId || '',
      }),
    );
    // 本地立刻停止：不等服务端确认
    this._stopLocal();
  }

  close() {
    this.ws?.close();
  }

  // ------------- 入站 -------------

  _handleAction(act) {
    switch (act.type) {
      case 'turn_start':
        this._currentTurnId = act.turn_id;
        this._sayChainTurnId = act.turn_id;
        this._sayChain = Promise.resolve();
        this.opts.onTurnStart?.(act.turn_id);
        break;

      case 'turn_end':
        this.opts.onTurnEnd?.(act.turn_id);
        if (this._currentTurnId === act.turn_id) {
          this._currentTurnId = null;
        }
        break;

      case 'stop':
        this._stopLocal();
        break;

      case 'motion':
        this.opts.live2d.playMotion(act.group, act.index ?? null, act.priority ?? 2);
        break;

      case 'thinking':
        this.opts.onThinking?.(act.text);
        break;

      case 'say':
        // 文字立即显示。但音频要按顺序播 —— 把文字也放进串行链，
        // 这样字幕和声音是对齐的。
        this._enqueueSay(act);
        break;

      case 'audio':
        this._enqueueAudio(act);
        break;

      case 'error':
        this.opts.onError?.(act.message || 'unknown error');
        break;

      default:
        console.warn('[ActionClient] unknown action', act);
    }
  }

  _stopLocal() {
    // 让当前播放停下，并把后续 say/audio 抛弃
    this.opts.live2d.stopSpeaking();
    // 通过 turnId 失效让 _enqueueAudio 跳过后续追加
    this._sayChainTurnId = null;
    this._sayChain = Promise.resolve();
  }

  _enqueueSay(sayAction) {
    const turnId = this._currentTurnId;
    // 等本轮串行链 + audio 抵达时一起处理。
    // 这里不直接显示，而是缓存等 audio 到达再一起出发；
    // 如果一直没 audio（TTS 失败），后端会直接发 say 不带 audio，那种情况兜底见下面。
    this._pendingSayByTurn = this._pendingSayByTurn || new Map();
    let arr = this._pendingSayByTurn.get(turnId);
    if (!arr) {
      arr = [];
      this._pendingSayByTurn.set(turnId, arr);
    }
    arr.push({ say: sayAction, hasAudio: false, _resolved: false });

    // 如果 5s 还没等到对应 audio，单独把字幕显示（兜底）
    setTimeout(() => {
      const list = this._pendingSayByTurn?.get(turnId);
      if (!list) return;
      const item = list.find((x) => x.say.id === sayAction.id);
      if (item && !item._resolved) {
        item._resolved = true;
        this.opts.onSay?.(sayAction.text);
      }
    }, 5000);
  }

  _enqueueAudio(audioAction) {
    const turnId = this._currentTurnId;
    if (this._sayChainTurnId !== turnId) {
      // 已经被 stop 或 turn 切换，丢弃
      return;
    }
    const url = this._absoluteAudioUrl(audioAction.url);

    this._sayChain = this._sayChain.then(async () => {
      if (this._sayChainTurnId !== turnId) return;
      // 找到对应 SayAction
      const list = this._pendingSayByTurn?.get(turnId);
      const item = list?.find((x) => x.say.id === audioAction.say_id);
      // 播放音频，音频开始时执行表情和显示字幕
      await this.opts.live2d.speak(url, {
        onStart: () => {
          // 音频开始时执行表情
          if (audioAction.expressions && audioAction.expressions.length > 0) {
            for (const expr of audioAction.expressions) {
              console.log('[ActionClient] 音频开始时执行表情:', expr.name);
              this.opts.live2d.setExpression(expr.name, expr.hold_ms ?? 0);
            }
          }
          // 音频开始时显示字幕
          if (item && !item._resolved) {
            item._resolved = true;
            this.opts.onSay?.(item.say.text);
          }
        },
      });
    });
  }

  _absoluteAudioUrl(u) {
    if (/^https?:\/\//.test(u)) return u;
    return `${this.audioBase}${u}`;
  }
}
