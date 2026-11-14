"use client";
import { LoadingState } from './ui/state';
import { InlineFeedback } from './ui/feedback';

import { Button } from './ui/button';
import { MetricCard } from './ui/metric-card';
import { ChartCard } from './ui/chart-card';
import { adminApi } from "../lib/api-client";

import { useEffect, useRef, useState } from "react";
import { init, use as registerECharts, type EChartsCoreOption } from "echarts/core";
import { LineChart, BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent, AriaComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import { FormSelect } from "./ui/form-controls";

registerECharts([LineChart,BarChart,GridComponent,TooltipComponent,LegendComponent,AriaComponent,SVGRenderer]);
type Day = {date:string; registered_users:number; visitors:number; tasks:number;completed:number;failed:number;new_users:number;active_users:number;input_tokens:number;output_tokens:number;cached_input_tokens:number;images:number;tts_characters:number;credits:number;settlements:number;settlements_with_usage:number};
type Metrics = {timezone:string;start:string;end:string;daily:Day[];registered_users:number;totals:Omit<Day,"date"|"registered_users"> & {tokens:number}};
const number = (value:number) => value.toLocaleString("zh-CN");

function Chart({option,label}:{option:EChartsCoreOption;label:string}) {
  const ref=useRef<HTMLDivElement>(null);
  const instance=useRef<ReturnType<typeof init>|null>(null);
  useEffect(()=>{
    if (!ref.current) return;
    const chart=init(ref.current,undefined,{renderer:"svg"});
    instance.current=chart;
    const observer=new ResizeObserver(()=>chart.resize());
    observer.observe(ref.current);
    return ()=>{observer.disconnect();chart.dispose();instance.current=null;};
  },[]);
  useEffect(()=>{instance.current?.setOption({...option,aria:{enabled:true,label:{description:label}}}, true);},[option,label]);
  return <div ref={ref} className="admin-chart" role="img" aria-label={label}/>;
}

export default function AdminDashboard() {
  const [days,setDays]=useState("30");
  const [data,setData]=useState<Metrics|null>(null);
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(true);
  const [revision,setRevision]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    setLoading(true);setError("");
    adminApi<Metrics>(`/dashboard?days=${days}`, {signal:controller.signal})
      .then(setData).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return ()=>controller.abort();
  },[days,revision]);
  const visible=data && !loading && !error ? data : null;
  function option(series:EChartsCoreOption["series"], headline = false): EChartsCoreOption {
    return {animation:false,aria:{enabled:true},color:["#a52238","#d6a74b","#6d907f"],tooltip:{trigger:"axis",confine:true},legend:{show:!headline,top:0,textStyle:{color:"#75685c"}},grid:{left:headline?48:60,right:14,top:headline?14:40,bottom:28},xAxis:{type:"category",data:visible?.daily.map(d=>d.date.slice(5)),axisLine:{lineStyle:{color:"#e5d8c6"}},axisLabel:{color:"#8e8276"}},yAxis:{type:"value",minInterval:1,splitLine:{lineStyle:{color:"#eee5d8"}},axisLabel:{color:"#8e8276"}},series};
  }
  const daily=visible?.daily||[];
  const today = daily.at(-1);
  return <section className="admin-dashboard" aria-label="使用看板">
    <div className="admin-dashboard-toolbar"><div><h2>使用看板</h2><p>{visible?`${visible.start} — ${visible.end}`:"每日使用情况"} · 北京时间</p></div><div className="admin-actions"><FormSelect ariaLabel="统计范围" value={days} options={[{value:"7",label:"最近 7 天"},{value:"30",label:"最近 30 天"},{value:"90",label:"最近 90 天"}]} onValueChange={setDays}/><Button variant="outline" disabled={loading} onClick={()=>setRevision(v=>v+1)}>刷新</Button></div></div>
    {loading?<LoadingState className="history-empty">正在加载看板…</LoadingState>:null}{error?<InlineFeedback as="div" className="feedback-block" >{error}</InlineFeedback>:null}
    {visible && today ? <>
      <div className="admin-dashboard-overview">
        <section className="admin-overview-panel admin-overview-growth" aria-labelledby="admin-growth-title">
          <h3 id="admin-growth-title">累计注册用户</h3>
          <div className="admin-overview-total">{number(visible.registered_users)}<span>人</span></div>
          <p className="admin-overview-note">所选日期新增 <strong>{number(visible.totals.new_users)}</strong> 人</p>
          <Chart label="累计注册用户趋势" option={option([{name:"累计注册用户",type:"line",symbol:"none",lineStyle:{width:2.5},areaStyle:{opacity:.08},data:daily.map(day=>day.registered_users)}], true)}/>
        </section>
        <section className="admin-overview-panel admin-overview-traffic" aria-labelledby="admin-traffic-title">
          <h3 id="admin-traffic-title">今日网站访客（UV）</h3>
          <div className="admin-overview-total">{number(today.visitors)}</div>
          <dl className="admin-overview-secondary">
            <div><dt>区间访客</dt><dd>{number(visible.totals.visitors)}</dd></div>
            <div><dt>今日新增用户</dt><dd>{number(today.new_users)}</dd></div>
          </dl>
          <Chart label="每日网站访客趋势" option={option([{name:"访客（UV）",type:"bar",barMaxWidth:14,itemStyle:{color:"#527765",borderRadius:[3,3,0,0]},data:daily.map(day=>day.visitors)}], true)}/>
        </section>
      </div>
      <h3 className="admin-dashboard-section-title">创作与消耗 <small>所选日期</small></h3>
      <div className="admin-metric-grid">
        <MetricCard variant="admin" label="创建任务" value={number(visible.totals.tasks)} caption={`已完成 ${number(visible.totals.completed)} · 失败 ${number(visible.totals.failed)}`} />
        <MetricCard variant="admin" label="发起创作用户" value={number(visible.totals.active_users)} caption="发起任务或生成操作的去重账号" />
        <MetricCard variant="admin" label="Token 消耗" value={number(visible.totals.tokens)} caption="已结算输入和输出 Token" />
        <MetricCard variant="admin" label="积分消耗" value={number(visible.totals.credits)} caption="已扣除积分，不包含冻结" />
      </div>
      <div className="admin-dashboard-charts">
        <ChartCard title="每日任务" caption={<>已完成任务按创建日期归组，以当前登记状态为准。</>}> <Chart label="每日创建任务和已完成任务趋势" option={option([{name:"创建任务",type:"bar",barMaxWidth:22,data:daily.map(d=>d.tasks)},{name:"已完成",type:"line",smooth:true,data:daily.map(d=>d.completed)}])}/></ChartCard>
        <ChartCard title="每日 Token 消耗" caption={<>按结算日期统计；缓存 Token 已包含在输入中。</>}> <Chart label="每日已结算输入和输出 Token" option={option([{name:"输入 Token",type:"bar",stack:"tokens",barMaxWidth:22,data:daily.map(d=>d.input_tokens)},{name:"输出 Token",type:"bar",stack:"tokens",barMaxWidth:22,data:daily.map(d=>d.output_tokens)}])}/></ChartCard>
        <ChartCard title="每日用户" caption={<>发起用户根据任务与生成操作统计，不代表登录活跃用户。</>}> <Chart label="每日发起用户与新增用户趋势" option={option([{name:"发起用户",type:"line",smooth:true,data:daily.map(d=>d.active_users)},{name:"新增用户",type:"line",smooth:true,data:daily.map(d=>d.new_users)}])}/></ChartCard>
        <ChartCard title="每日积分消耗" caption={<>已结算图片 {number(visible.totals.images)} 张 · 语音 {number(visible.totals.tts_characters)} 字符</>}> <Chart label="每日已扣除积分趋势" option={option([{name:"积分",type:"bar",barMaxWidth:22,data:daily.map(d=>d.credits)}])}/></ChartCard>
      </div>
      <p className="admin-dashboard-coverage">统计口径：{visible.totals.settlements} 笔已结算操作，其中 {visible.totals.settlements_with_usage} 笔含用量记录。未记录、失败或尚未结算的用量未计入 Token；历史缺失数据不作估算。</p>
      <p className="admin-dashboard-coverage">网站访客覆盖官网、教师资源广场、工作台和独立游戏播放器。同源页面按浏览器去重，跨域名或设备可能重复计数。流量数据从开始采集时累计。</p>
    </>:null}
  </section>;
}
