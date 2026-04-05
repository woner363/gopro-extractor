const { spawn } = require('child_process');
const { EventEmitter } = require('events');
const path = require('path');

class PythonBridge extends EventEmitter {
  constructor(pythonPath, backendDir, configPath) {
    super();
    this.pythonPath = pythonPath;
    this.backendDir = backendDir;
    this.configPath = configPath;
    this.process = null;
    this.requestId = 0;
    this.pending = new Map();
    this.buffer = '';
  }

  start() {
    let args;
    if (this.pythonPath.endsWith('.py') || this.pythonPath.includes('python')) {
      // Development: python3 main.py [config]
      const mainScript = path.join(this.backendDir, 'main.py');
      args = [mainScript];
      if (this.configPath) args.push(this.configPath);
    } else {
      // Production: bundled executable [config]
      args = [];
      if (this.configPath) args.push(this.configPath);
    }

    this.process = spawn(this.pythonPath, args, {
      cwd: this.backendDir,
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    this.process.stdout.on('data', (data) => {
      this.buffer += data.toString();
      const lines = this.buffer.split('\n');
      this.buffer = lines.pop(); // Keep incomplete line in buffer

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const msg = JSON.parse(line);
          this._handleMessage(msg);
        } catch (e) {
          console.error('Failed to parse Python output:', line);
        }
      }
    });

    this.process.stderr.on('data', (data) => {
      console.error('Python stderr:', data.toString());
    });

    this.process.on('close', (code) => {
      console.log('Python process exited with code', code);
      // Reject all pending requests
      for (const [id, { reject }] of this.pending) {
        reject(new Error('Python process exited'));
      }
      this.pending.clear();
    });
  }

  _handleMessage(msg) {
    if (msg.id !== undefined && msg.id !== null) {
      // Response to a request
      const pending = this.pending.get(msg.id);
      if (pending) {
        this.pending.delete(msg.id);
        if (msg.error) {
          pending.reject(new Error(msg.error.message || JSON.stringify(msg.error)));
        } else {
          pending.resolve(msg.result);
        }
      }
    } else if (msg.method) {
      // Notification from Python
      this.emit('notification', msg.method, msg.params || {});
    }
  }

  call(method, params = {}, timeout = 0) { // 0 = no timeout for long backups
    return new Promise((resolve, reject) => {
      if (!this.process) {
        return reject(new Error('Python process not running'));
      }

      const id = ++this.requestId;
      const request = { jsonrpc: '2.0', method, params, id };

      let timer;
      if (timeout > 0) {
        timer = setTimeout(() => {
          this.pending.delete(id);
          reject(new Error(`Request ${method} timed out after ${timeout}ms`));
        }, timeout);
      }

      this.pending.set(id, {
        resolve: (result) => { if (timer) clearTimeout(timer); resolve(result); },
        reject: (err) => { if (timer) clearTimeout(timer); reject(err); },
      });

      this.process.stdin.write(JSON.stringify(request) + '\n');
    });
  }

  stop() {
    if (this.process) {
      this.process.stdin.end();
      this.process.kill();
      this.process = null;
    }
  }
}

module.exports = { PythonBridge };
