import 'jasmine';
import {createStatsViewer, StatsViewerElement} from './stats';

interface InternalStatsViewer {
  batteryCtx: CanvasRenderingContext2D | null;
  batteryCanvas: HTMLCanvasElement | null;
  drawBatteryChart: () => void;
  statsHistory: {
    ack: number[];
    step: number[];
    transit: number[];
    charge: number[];
    current: number[];
  };
}

describe('StatsViewerElement', () => {
  let statsViewer: StatsViewerElement;
  let statsToggle: HTMLButtonElement;
  let statsPanel: HTMLDialogElement;
  let statsClose: HTMLButtonElement;
  let statAck: HTMLElement;
  let statStep: HTMLElement;
  let statTransit: HTMLElement;
  let statQueue: HTMLElement;
  let statsCanvas: HTMLCanvasElement;
  let batteryCanvas: HTMLCanvasElement;

  beforeEach(() => {
    document.body.innerHTML = `
      <button id="stats-toggle">Stats</button>
    `;
    statsViewer = createStatsViewer();
    statsViewer.id = 'stats-viewer';
    document.body.appendChild(statsViewer);

    statsToggle = document.getElementById('stats-toggle') as HTMLButtonElement;
    statsPanel = statsViewer.querySelector('#stats-panel') as HTMLDialogElement;
    statsClose = statsViewer.querySelector('#stats-close') as HTMLButtonElement;
    statAck = statsViewer.querySelector('#stat-ack') as HTMLElement;
    statStep = statsViewer.querySelector('#stat-step') as HTMLElement;
    statTransit = statsViewer.querySelector('#stat-transit') as HTMLElement;
    statQueue = statsViewer.querySelector('#stat-queue') as HTMLElement;
    statsCanvas = statsViewer.querySelector(
      '#stats-chart'
    ) as HTMLCanvasElement;
    batteryCanvas = statsViewer.querySelector(
      '#stats-battery-chart'
    ) as HTMLCanvasElement;

    statsPanel.show = jasmine.createSpy('show');
    statsPanel.close = jasmine.createSpy('close');

    statsToggle.addEventListener('click', () => {
      statsViewer.showPanel();
    });
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('initializes custom element, canvas and elements with exact DOM structure', () => {
    expect(statsViewer).toBeTruthy();
    expect(statsViewer.tagName.toLowerCase()).toBe('stats-viewer');
    expect(statsCanvas).toBeTruthy();
    expect(statsPanel).toBeTruthy();

    const expectedHtml =
      '<div class="stats-header"><h3>Stats for Nerds</h3><button id="stats-close">\u00d7</button></div>' +
      '<div class="stat-line"><span title="Round-trip time for frames. Measures network latency + client rendering time.">ACK Latency:</span><span><span id="stat-ack">-</span> ms</span></div>' +
      '<div class="stat-line"><span title="Time taken by the emulator to process the action and return the next frame.">Env Step:</span><span><span id="stat-step">-</span> ms</span></div>' +
      '<div class="stat-line"><span title="Time taken for the action to travel from the browser client to the server.">Action Transit:</span><span><span id="stat-transit">-</span> ms</span></div>' +
      '<div class="stat-line"><span title="Time the action spent waiting in the server queue before being processed.">Action Queue:</span><span><span id="stat-queue">-</span> ms</span></div>' +
      '<canvas id="stats-chart" width="400" height="150" style="border: 1px solid rgb(85, 85, 85); margin-top: 10px;"></canvas>' +
      '<hr style="border-color: rgb(68, 68, 68); margin: 8px 0px;">' +
      '<div style="font-weight: bold; margin-bottom: 4px; color: rgb(138, 180, 248);">Phone / Device Metrics</div>' +
      '<div class="stat-line"><span title="Battery charge level percentage [0-100]">Battery Level:</span><span><span id="stat-battery-level">-</span> %</span></div>' +
      '<div class="stat-line"><span title="Battery charging status (e.g. CHARGING, DISCHARGING)">Status:</span><span><span id="stat-battery-status">-</span></span></div>' +
      '<div class="stat-line"><span title="Power source (AC, USB, WIRELESS, UNPLUGGED)">Source:</span><span><span id="stat-battery-source">-</span></span></div>' +
      '<div class="stat-line"><span title="Battery voltage in millivolts">Voltage:</span><span><span id="stat-battery-voltage">-</span> mV</span></div>' +
      '<div class="stat-line"><span title="Instantaneous current in microamperes">Current:</span><span><span id="stat-battery-current">-</span> \u03bcA</span></div>' +
      '<div class="stat-line"><span title="Instantaneous power in milliwatts">Power:</span><span><span id="stat-battery-power">-</span> mW</span></div>' +
      '<div class="stat-line"><span title="Battery temperature in degrees Celsius">Temp:</span><span><span id="stat-battery-temp">-</span> \u00b0C</span></div>' +
      '<div class="stat-line"><span title="Remaining charge counter in microampere-hours">Charge Counter:</span><span><span id="stat-battery-counter">-</span> \u03bcAh</span></div>' +
      '<div class="stat-line"><span title="Total remaining energy in nanowatt-hours">Energy:</span><span><span id="stat-battery-energy">-</span> nWh</span></div>' +
      '<canvas id="stats-battery-chart" width="400" height="150" style="border: 1px solid rgb(85, 85, 85); margin-top: 10px;"></canvas>';
    expect(statsPanel.innerHTML).toBe(expectedHtml);

    // Calling connectedCallback again is idempotent
    statsViewer.connectedCallback();
    expect(statsViewer.children.length).toBe(1);
  });

  it('updates stat text content when receiving stats data', () => {
    statsViewer.handleStats({
      ack_latency: 12.34,
      env_step_ms: 5.67,
      action_transit_ms: 8.91,
      action_queue_ms: 1.23,
    });

    expect(statAck.innerText).toBe('12.34');
    expect(statStep.innerText).toBe('5.67');
    expect(statTransit.innerText).toBe('8.91');
    expect(statQueue.innerText).toBe('1.23');
  });

  it('opens panel and renders chart on new stats', () => {
    const ctx = statsCanvas.getContext('2d')!;
    spyOn(ctx, 'clearRect').and.callThrough();
    spyOn(ctx, 'fillText').and.callThrough();
    spyOn(ctx, 'fillRect').and.callThrough();
    spyOn(ctx, 'stroke').and.callThrough();

    statsToggle.click();
    expect(statsPanel.show).toHaveBeenCalled();

    for (let i = 0; i < 105; i++) {
      statsViewer.handleStats({
        ack_latency: 10 + i,
        env_step_ms: 20 + i,
        action_transit_ms: 30 + i,
        action_queue_ms: 5,
      });
    }

    expect(statAck.innerText).toBe('114.00');
    const internalViewer = statsViewer as unknown as InternalStatsViewer;
    expect(internalViewer.statsHistory.ack.length).toBe(100);
    expect(ctx.clearRect).toHaveBeenCalledWith(0, 0, 400, 150);
    expect(ctx.fillText).toHaveBeenCalledWith('ACK', 25, 18);
    expect(ctx.fillText).toHaveBeenCalledWith('Step', 85, 18);
    expect(ctx.fillText).toHaveBeenCalledWith('Transit', 145, 18);
    expect(ctx.fillRect).toHaveBeenCalledWith(10, 10, 10, 10);
    expect(ctx.fillRect).toHaveBeenCalledWith(70, 10, 10, 10);
    expect(ctx.fillRect).toHaveBeenCalledWith(130, 10, 10, 10);
    expect(ctx.stroke).toHaveBeenCalled();
  });

  it('closes panel when close button is clicked or close event triggers and stops drawing', () => {
    const ctx = statsCanvas.getContext('2d')!;
    const clearSpy = spyOn(ctx, 'clearRect').and.callThrough();

    statsViewer.showPanel();
    clearSpy.calls.reset();

    statsClose.click();
    expect(statsPanel.close).toHaveBeenCalled();
    statsViewer.handleStats({ack_latency: 10});
    expect(clearSpy).not.toHaveBeenCalled();

    statsViewer.showPanel();
    clearSpy.calls.reset();

    statsPanel.dispatchEvent(new Event('close'));
    statsViewer.handleStats({ack_latency: 20});
    expect(clearSpy).not.toHaveBeenCalled();
  });

  it('handles empty or partial stats objects and single data point chart rendering', () => {
    statsToggle.click();

    // Partial stats object
    statsViewer.handleStats({
      ack_latency: 10.0,
    });

    expect(statAck.innerText).toBe('10.00');
    expect(statStep.innerText).toBe('-');

    // Empty stats object
    statsViewer.handleStats({});
  });

  it('updates phone / device metrics when receiving battery stats data', () => {
    const internalViewer = statsViewer as unknown as InternalStatsViewer;
    expect(internalViewer.batteryCtx).not.toBeNull();

    statsViewer.handleStats({
      battery_power: {
        level_percent: 85,
        status: 'CHARGING',
        plugged_source: 'AC',
        voltage_mv: 4200,
        current_now_ua: 500000,
        power_mw: 2100.0,
        temperature_celsius: 28.5,
        charge_counter_uah: 3000000,
        energy_counter_nwh: 11100000000,
      },
    });

    expect(
      (statsViewer.querySelector('#stat-battery-level') as HTMLElement).innerText
    ).toBe('85');
    expect(
      (statsViewer.querySelector('#stat-battery-status') as HTMLElement).innerText
    ).toBe('CHARGING');
    expect(
      (statsViewer.querySelector('#stat-battery-source') as HTMLElement).innerText
    ).toBe('AC');
    expect(
      (statsViewer.querySelector('#stat-battery-voltage') as HTMLElement).innerText
    ).toBe('4200');
    expect(
      (statsViewer.querySelector('#stat-battery-current') as HTMLElement).innerText
    ).toBe('500000');
    expect(
      (statsViewer.querySelector('#stat-battery-power') as HTMLElement).innerText
    ).toBe('2100.00');
    expect(
      (statsViewer.querySelector('#stat-battery-temp') as HTMLElement).innerText
    ).toBe('28.5');
    expect(
      (statsViewer.querySelector('#stat-battery-counter') as HTMLElement).innerText
    ).toBe('3000000');
    expect(
      (statsViewer.querySelector('#stat-battery-energy') as HTMLElement).innerText
    ).toBe('11100000000');
  });

  it('handles zero current_now_ua correctly', () => {
    statsViewer.handleStats({
      battery_power: {
        current_now_ua: 0,
      },
    });

    expect(
      (statsViewer.querySelector('#stat-battery-current') as HTMLElement).innerText
    ).toBe('0');
    const internalViewer = statsViewer as unknown as InternalStatsViewer;
    expect(internalViewer.statsHistory.current).toContain(0);
  });

  it('positions phone / device metrics below stats-chart in DOM order', () => {
    const chartElem = statsViewer.querySelector('#stats-chart') as HTMLElement;
    const batteryElem = statsViewer.querySelector(
      '#stat-battery-level'
    ) as HTMLElement;
    const isAfter =
      (chartElem.compareDocumentPosition(batteryElem) &
        Node.DOCUMENT_POSITION_FOLLOWING) !==
      0;
    expect(isAfter).toBeTrue();
  });

  it('renders battery charge and current line diagram on stats-battery-chart', () => {
    const internalViewer = statsViewer as unknown as InternalStatsViewer;
    const batteryCtx = batteryCanvas.getContext('2d')!;
    spyOn(batteryCtx, 'clearRect').and.callThrough();
    spyOn(batteryCtx, 'fillText').and.callThrough();
    spyOn(batteryCtx, 'fillRect').and.callThrough();
    spyOn(batteryCtx, 'stroke').and.callThrough();
    const drawBatterySpy = spyOn(
      internalViewer,
      'drawBatteryChart'
    ).and.callThrough();
    statsToggle.click();
    expect(statsPanel.show).toHaveBeenCalled();
    expect(drawBatterySpy).toHaveBeenCalled();

    for (let i = 0; i < 5; i++) {
      statsViewer.handleStats({
        battery_power: {
          level_percent: 80 + i,
          current_now_ua: i % 2 === 0 ? 500000 : -200000,
        },
      });
    }

    expect(
      (statsViewer.querySelector('#stat-battery-level') as HTMLElement).innerText
    ).toBe('84');
    expect(
      (statsViewer.querySelector('#stat-battery-current') as HTMLElement).innerText
    ).toBe('500000');
    expect(batteryCanvas).toBeTruthy();
    expect(internalViewer.statsHistory.charge).toEqual([
      80, 81, 82, 83, 84,
    ]);
    expect(batteryCtx.clearRect).toHaveBeenCalledWith(0, 0, 400, 150);
    expect(batteryCtx.fillText).toHaveBeenCalledWith('Charge (%)', 25, 18);
    expect(batteryCtx.fillText).toHaveBeenCalledWith(
      'Current (\u03bcA)',
      115,
      18
    );
    expect(batteryCtx.fillRect).toHaveBeenCalledWith(10, 10, 10, 10);
    expect(batteryCtx.fillRect).toHaveBeenCalledWith(100, 10, 10, 10);
    expect(batteryCtx.stroke).toHaveBeenCalled();
  });

  it('renders battery chart correctly when current values are uniform', () => {
    statsToggle.click();
    expect(statsPanel.show).toHaveBeenCalled();

    for (let i = 0; i < 3; i++) {
      statsViewer.handleStats({
        battery_power: {
          level_percent: 50,
          current_now_ua: 300000,
        },
      });
    }

    expect(
      (statsViewer.querySelector('#stat-battery-level') as HTMLElement).innerText
    ).toBe('50');
    expect(
      (statsViewer.querySelector('#stat-battery-current') as HTMLElement).innerText
    ).toBe('300000');
    const internalViewer = statsViewer as unknown as InternalStatsViewer;
    expect(internalViewer.statsHistory.current).toEqual([
      300000, 300000, 300000,
    ]);
  });

  it('updates episode and KPI badge cards when present in DOM', () => {
    document.body.innerHTML += `
      <div id="kpi-step"></div>
      <div id="kpi-reward"></div>
      <div id="pkg-badge"></div>
      <div id="kpi-latency"></div>
      <div id="kpi-battery"></div>
    `;

    statsViewer.handleStats({
      ack_latency: 15.5,
      env_step_ms: 22.3,
      episode: {
        step: 42,
        step_type: 'MID',
        reward: 1.0,
        cumulative_reward: 10.5,
        active_package: 'com.android.settings',
      },
      battery_power: {
        level_percent: 85,
        power_mw: 1200,
      },
    });

    expect(document.getElementById('kpi-step')!.textContent).toBe('42 (MID)');
    expect(document.getElementById('kpi-reward')!.textContent).toBe('10.5 (+1.0)');
    expect(document.getElementById('pkg-badge')!.textContent).toBe('pkg: settings');
    expect(document.getElementById('kpi-latency')!.textContent).toBe('15.5 / 22.3 ms');
    expect(document.getElementById('kpi-battery')!.textContent).toBe('85% · 1200mW');
  });
});


