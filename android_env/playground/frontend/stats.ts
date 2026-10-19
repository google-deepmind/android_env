
/**
 * Interface representing battery and power telemetry statistics.
 */
export interface BatteryPowerStatsData {
  level_percent?: number;
  current_now_ua?: number;
  voltage_mv?: number;
  power_mw?: number;
  temperature_celsius?: number;
  status?: string;
  plugged_source?: string;
  charge_counter_uah?: number;
  thermal_status?: number;
  energy_counter_nwh?: number;
}

/**
 * Interface representing RL episode telemetry metrics.
 */
export interface EpisodeStatsData {
  step?: number;
  reward?: number;
  cumulative_reward?: number;
  step_type?: string;
  active_package?: string;
}

/**
 * Interface representing performance stats from the server.
 */
export interface StatsData {
  ack_latency?: number;
  env_step_ms?: number;
  action_transit_ms?: number;
  action_queue_ms?: number;
  battery_power?: BatteryPowerStatsData;
  episode?: EpisodeStatsData;
}

/**
 * Custom Web Component for rendering and managing "Stats for Nerds" in the Playground UI.
 */
export class StatsViewerElement extends HTMLElement {
  private statsPanel: HTMLDialogElement | null = null;
  private statsClose: HTMLButtonElement | null = null;
  private statAck: HTMLElement | null = null;
  private statStep: HTMLElement | null = null;
  private statTransit: HTMLElement | null = null;
  private statQueue: HTMLElement | null = null;
  private statsCanvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private statBatteryLevel: HTMLElement | null = null;
  private statBatteryStatus: HTMLElement | null = null;
  private statBatterySource: HTMLElement | null = null;
  private statBatteryVoltage: HTMLElement | null = null;
  private statBatteryCurrent: HTMLElement | null = null;
  private statBatteryPower: HTMLElement | null = null;
  private statBatteryTemp: HTMLElement | null = null;
  private statBatteryCounter: HTMLElement | null = null;
  private statBatteryEnergy: HTMLElement | null = null;
  private batteryCanvas: HTMLCanvasElement | null = null;
  private batteryCtx: CanvasRenderingContext2D | null = null;

  private showStats = false;
  private readonly maxDataPoints = 100;
  private readonly statsHistory: {
    ack: number[];
    step: number[];
    transit: number[];
    charge: number[];
    current: number[];
  } = {
    ack: [],
    step: [],
    transit: [],
    charge: [],
    current: [],
  };

  constructor() {
    super();
  }

  /** @export */
  connectedCallback(): void {
    if (!this.statsPanel) {
      const panel = document.createElement('dialog');
      panel.id = 'stats-panel';

      const header = document.createElement('div');
      header.className = 'stats-header';

      const title = document.createElement('h3');
      title.textContent = 'Stats for Nerds';

      this.statsClose = document.createElement('button');
      this.statsClose.id = 'stats-close';
      this.statsClose.textContent = '\u00d7';

      header.appendChild(title);
      header.appendChild(this.statsClose);
      panel.appendChild(header);

      const addStatLine = (
        label: string,
        id: string,
        unit: string,
        tooltip: string
      ): HTMLElement => {
        const line = document.createElement('div');
        line.className = 'stat-line';
        const labelSpan = document.createElement('span');
        labelSpan.title = tooltip;
        labelSpan.textContent = label + ':';
        const valContainer = document.createElement('span');
        const valSpan = document.createElement('span');
        valSpan.id = id;
        valSpan.textContent = '-';
        valContainer.appendChild(valSpan);
        if (unit) {
          valContainer.appendChild(document.createTextNode(' ' + unit));
        }
        line.appendChild(labelSpan);
        line.appendChild(valContainer);
        panel.appendChild(line);
        return valSpan;
      };

      this.statAck = addStatLine(
        'ACK Latency',
        'stat-ack',
        'ms',
        'Round-trip time for frames. Measures network latency + client rendering time.'
      );
      this.statStep = addStatLine(
        'Env Step',
        'stat-step',
        'ms',
        'Time taken by the emulator to process the action and return the next frame.'
      );
      this.statTransit = addStatLine(
        'Action Transit',
        'stat-transit',
        'ms',
        'Time taken for the action to travel from the browser client to the server.'
      );
      this.statQueue = addStatLine(
        'Action Queue',
        'stat-queue',
        'ms',
        'Time the action spent waiting in the server queue before being processed.'
      );

      this.statsCanvas = document.createElement('canvas');
      this.statsCanvas.id = 'stats-chart';
      this.statsCanvas.width = 400;
      this.statsCanvas.height = 150;
      this.statsCanvas.style.cssText = 'border: 1px solid #555; margin-top: 10px;';
      panel.appendChild(this.statsCanvas);

      const hr = document.createElement('hr');
      hr.style.cssText = 'border-color: #444; margin: 8px 0;';
      panel.appendChild(hr);

      const batteryHeader = document.createElement('div');
      batteryHeader.style.cssText =
        'font-weight: bold; margin-bottom: 4px; color: #8ab4f8;';
      batteryHeader.textContent = 'Phone / Device Metrics';
      panel.appendChild(batteryHeader);

      this.statBatteryLevel = addStatLine(
        'Battery Level',
        'stat-battery-level',
        '%',
        'Battery charge level percentage [0-100]'
      );
      this.statBatteryStatus = addStatLine(
        'Status',
        'stat-battery-status',
        '',
        'Battery charging status (e.g. CHARGING, DISCHARGING)'
      );
      this.statBatterySource = addStatLine(
        'Source',
        'stat-battery-source',
        '',
        'Power source (AC, USB, WIRELESS, UNPLUGGED)'
      );
      this.statBatteryVoltage = addStatLine(
        'Voltage',
        'stat-battery-voltage',
        'mV',
        'Battery voltage in millivolts'
      );
      this.statBatteryCurrent = addStatLine(
        'Current',
        'stat-battery-current',
        '\u03bcA',
        'Instantaneous current in microamperes'
      );
      this.statBatteryPower = addStatLine(
        'Power',
        'stat-battery-power',
        'mW',
        'Instantaneous power in milliwatts'
      );
      this.statBatteryTemp = addStatLine(
        'Temp',
        'stat-battery-temp',
        '\u00b0C',
        'Battery temperature in degrees Celsius'
      );
      this.statBatteryCounter = addStatLine(
        'Charge Counter',
        'stat-battery-counter',
        '\u03bcAh',
        'Remaining charge counter in microampere-hours'
      );
      this.statBatteryEnergy = addStatLine(
        'Energy',
        'stat-battery-energy',
        'nWh',
        'Total remaining energy in nanowatt-hours'
      );

      this.batteryCanvas = document.createElement('canvas');
      this.batteryCanvas.id = 'stats-battery-chart';
      this.batteryCanvas.width = 400;
      this.batteryCanvas.height = 150;
      this.batteryCanvas.style.cssText =
        'border: 1px solid #555; margin-top: 10px;';
      panel.appendChild(this.batteryCanvas);

      this.appendChild(panel);
      this.statsPanel = panel;
      this.ctx = this.statsCanvas.getContext('2d');
      this.batteryCtx = this.batteryCanvas.getContext('2d');
      this.initEventListeners();
    }
  }

  private initEventListeners(): void {
    this.statsClose!.addEventListener('click', () => {
      this.hidePanel();
    });

    this.statsPanel!.addEventListener('close', () => {
      this.showStats = false;
    });
  }

  /** @export */
  showPanel(): void {
    this.showStats = true;
    this.statsPanel!.show();
    this.drawChart();
    this.drawBatteryChart();
  }

  /** @export */
  hidePanel(): void {
    this.showStats = false;
    this.statsPanel!.close();
  }

  /** @export */
  togglePanel(): void {
    if (this.showStats) {
      this.hidePanel();
    } else {
      this.showPanel();
    }
  }

  /** @export */
  handleStats(stats: StatsData): void {
    if (stats.ack_latency !== undefined) {
      this.statAck!.innerText = stats.ack_latency.toFixed(2);
      this.pushStat(this.statsHistory.ack, stats.ack_latency);
    }
    if (stats.env_step_ms !== undefined) {
      this.statStep!.innerText = stats.env_step_ms.toFixed(2);
      this.pushStat(this.statsHistory.step, stats.env_step_ms);
    }
    if (stats.action_transit_ms !== undefined) {
      this.statTransit!.innerText = stats.action_transit_ms.toFixed(2);
      this.pushStat(this.statsHistory.transit, stats.action_transit_ms);
    }
    if (stats.action_queue_ms !== undefined) {
      this.statQueue!.innerText = stats.action_queue_ms.toFixed(2);
    }
    if (stats.battery_power) {
      const b = stats.battery_power;
      if (b.level_percent !== undefined) {
        this.statBatteryLevel!.innerText = b.level_percent.toString();
        this.pushStat(this.statsHistory.charge, b.level_percent);
      }
      if (b.status !== undefined) {
        this.statBatteryStatus!.innerText = b.status;
      }
      if (b.plugged_source !== undefined) {
        this.statBatterySource!.innerText = b.plugged_source;
      }
      if (b.voltage_mv !== undefined) {
        this.statBatteryVoltage!.innerText = b.voltage_mv.toString();
      }
      if (b.current_now_ua !== undefined) {
        this.statBatteryCurrent!.innerText = b.current_now_ua.toString();
        this.pushStat(this.statsHistory.current, b.current_now_ua);
      }
      if (b.power_mw !== undefined) {
        this.statBatteryPower!.innerText = b.power_mw.toFixed(2);
      }
      if (b.temperature_celsius !== undefined) {
        this.statBatteryTemp!.innerText = b.temperature_celsius.toFixed(1);
      }
      if (b.charge_counter_uah !== undefined) {
        this.statBatteryCounter!.innerText = b.charge_counter_uah.toString();
      }
      if (b.energy_counter_nwh !== undefined) {
        this.statBatteryEnergy!.innerText = b.energy_counter_nwh.toString();
      }
    }

    if (stats.episode) {
      const ep = stats.episode;
      const kpiStep = document.getElementById('kpi-step');
      if (kpiStep && ep.step !== undefined) {
        kpiStep.textContent = `${ep.step} (${ep.step_type ?? 'MID'})`;
      }
      const kpiReward = document.getElementById('kpi-reward');
      if (kpiReward && ep.cumulative_reward !== undefined) {
        const r = ep.reward ?? 0;
        kpiReward.textContent = `${ep.cumulative_reward.toFixed(1)} (+${r.toFixed(1)})`;
      }
      const pkgBadge = document.getElementById('pkg-badge');
      if (pkgBadge && ep.active_package) {
        const shortName =
          ep.active_package.split('.').pop() || ep.active_package;
        pkgBadge.textContent = `pkg: ${shortName}`;
      }
    }

    const kpiLatency = document.getElementById('kpi-latency');
    if (
      kpiLatency &&
      (stats.ack_latency !== undefined || stats.env_step_ms !== undefined)
    ) {
      kpiLatency.textContent = `${(stats.ack_latency ?? 0).toFixed(1)} / ${(stats.env_step_ms ?? 0).toFixed(1)} ms`;
    }

    const kpiBattery = document.getElementById('kpi-battery');
    if (
      kpiBattery &&
      stats.battery_power &&
      stats.battery_power.level_percent !== undefined
    ) {
      kpiBattery.textContent = `${stats.battery_power.level_percent}% · ${(stats.battery_power.power_mw ?? 0).toFixed(0)}mW`;
    }

    if (this.showStats) {
      this.drawChart();
      this.drawBatteryChart();
    }
  }

  private pushStat(arr: number[], val: number): void {
    arr.push(val);
    if (arr.length > this.maxDataPoints) {
      arr.shift();
    }
  }

  private drawChart(): void {
    const width = this.statsCanvas!.width;
    const height = this.statsCanvas!.height;
    const ctx = this.ctx!;
    ctx.clearRect(0, 0, width, height);

    let maxVal = 100;
    for (const key of ['ack', 'step', 'transit'] as const) {
      if (this.statsHistory[key].length > 0) {
        maxVal = Math.max(maxVal, ...this.statsHistory[key]);
      }
    }
    maxVal = maxVal * 1.2;

    ctx.strokeStyle = '#444';
    ctx.lineWidth = 1;
    for (let i = 1; i < 4; i++) {
      const y = height * (i / 4);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();

      ctx.fillStyle = '#aaa';
      ctx.font = '10px sans-serif';
      ctx.fillText((maxVal * (1 - i / 4)).toFixed(0) + ' ms', 5, y - 2);
    }

    this.drawPlot(this.statsHistory.ack, '#ff8a80', maxVal);
    this.drawPlot(this.statsHistory.step, '#b9f6ca', maxVal);
    this.drawPlot(this.statsHistory.transit, '#82b1ff', maxVal);

    ctx.fillStyle = '#ff8a80';
    ctx.fillRect(10, 10, 10, 10);
    ctx.fillStyle = '#e8eaed';
    ctx.fillText('ACK', 25, 18);

    ctx.fillStyle = '#b9f6ca';
    ctx.fillRect(70, 10, 10, 10);
    ctx.fillStyle = '#e8eaed';
    ctx.fillText('Step', 85, 18);

    ctx.fillStyle = '#82b1ff';
    ctx.fillRect(130, 10, 10, 10);
    ctx.fillStyle = '#e8eaed';
    ctx.fillText('Transit', 145, 18);
  }

  private drawPlot(data: number[], color: string, maxVal: number): void {
    this.drawSeries(this.ctx!, this.statsCanvas!, data, color, 0, maxVal);
  }

  private drawSeries(
    ctx: CanvasRenderingContext2D,
    canvas: HTMLCanvasElement,
    data: number[],
    color: string,
    minVal: number,
    maxVal: number
  ): void {
    if (data.length < 2) return;
    const width = canvas.width;
    const height = canvas.height;
    const range = maxVal - minVal || 1;
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    const stepX = width / (this.maxDataPoints - 1);
    const startX = width - (data.length - 1) * stepX;

    const getY = (val: number) => {
      const fraction = (val - minVal) / range;
      const clamped = Math.max(0, Math.min(1, fraction));
      return height - clamped * height;
    };

    ctx.moveTo(startX, getY(data[0]));
    for (let i = 1; i < data.length; i++) {
      const x = startX + i * stepX;
      ctx.lineTo(x, getY(data[i]));
    }
    ctx.stroke();
  }

  private drawBatteryChart(): void {
    const width = this.batteryCanvas!.width;
    const height = this.batteryCanvas!.height;
    const batteryCtx = this.batteryCtx!;
    batteryCtx.clearRect(0, 0, width, height);

    let minCurrent = 0;
    let maxCurrent = 100;
    if (this.statsHistory.current.length > 0) {
      minCurrent = Math.min(0, ...this.statsHistory.current);
      maxCurrent = Math.max(100, ...this.statsHistory.current);
    }
    maxCurrent = maxCurrent * 1.2;

    batteryCtx.strokeStyle = '#444';
    batteryCtx.lineWidth = 1;
    for (let i = 1; i < 4; i++) {
      const y = height * (i / 4);
      batteryCtx.beginPath();
      batteryCtx.moveTo(0, y);
      batteryCtx.lineTo(width, y);
      batteryCtx.stroke();

      batteryCtx.fillStyle = '#aaa';
      batteryCtx.font = '10px sans-serif';
      batteryCtx.fillText(`${(100 * (1 - i / 4)).toFixed(0)}%`, 5, y - 2);

      const currentVal = `${(
        minCurrent +
        (maxCurrent - minCurrent) * (1 - i / 4)
      ).toFixed(0)} \u03bcA`;
      const textWidth = batteryCtx.measureText(currentVal).width;
      batteryCtx.fillText(currentVal, width - textWidth - 5, y - 2);
    }

    this.drawSeries(
      batteryCtx,
      this.batteryCanvas!,
      this.statsHistory.charge,
      '#00e676',
      0,
      100
    );
    this.drawSeries(
      batteryCtx,
      this.batteryCanvas!,
      this.statsHistory.current,
      '#ffd54f',
      minCurrent,
      maxCurrent
    );

    batteryCtx.fillStyle = '#00e676';
    batteryCtx.fillRect(10, 10, 10, 10);
    batteryCtx.fillStyle = '#e8eaed';
    batteryCtx.font = '10px sans-serif';
    batteryCtx.fillText('Charge (%)', 25, 18);

    batteryCtx.fillStyle = '#ffd54f';
    batteryCtx.fillRect(100, 10, 10, 10);
    batteryCtx.fillStyle = '#e8eaed';
    batteryCtx.fillText('Current (\u03bcA)', 115, 18);
  }
}

if (!customElements.get('stats-viewer')) {
  customElements.define('stats-viewer', StatsViewerElement);
}

/**
 * Helper factory function to instantiate and upgrade a StatsViewerElement.
 */
export function createStatsViewer(): StatsViewerElement {
  return document.createElement('stats-viewer') as StatsViewerElement;
}
