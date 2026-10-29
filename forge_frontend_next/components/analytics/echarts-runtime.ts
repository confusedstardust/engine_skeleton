import { init, use as registerCharts } from 'echarts/core';
import { BarChart, PieChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent, GraphicComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

registerCharts([BarChart, PieChart, GridComponent, LegendComponent, TooltipComponent, GraphicComponent, CanvasRenderer]);
export { init };
