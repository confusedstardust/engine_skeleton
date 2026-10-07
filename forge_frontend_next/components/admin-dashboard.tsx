"use client";

import { useEffect, useRef, useState } from "react";
import { init, use as registerECharts, type EChartsCoreOption } from "echarts/core";
import { LineChart, BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent, AriaComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import { FormSelect } from "./ui/form-controls";
import { withBasePath } from "../app/base-path";

registerECharts([LineChart,BarChart,GridComponent,TooltipComponent,LegendComponent,AriaComponent,SVGRenderer]);
type Day = {date:string; tasks:number;completed:number;failed:number;new_users:number;active_users:number;input_tokens:number;output_tokens:number;cached_input_tokens:number;images:number;tts_characters:number;credits:number;settlements:number;settlements_with_usage:number};
type Metrics = {timezone:string;start:string;end:string;daily:Day[];totals:Omit<Day,"date"> & {tokens:number}};
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
  const [tablePage,setTablePage]=useState(1);
  useEffect(()=>{
    const controller=new AbortController();
    setLoading(true);setError("");
    fetch(withBasePath(`/api/forge/admin/dashboard?days=${days}`),{credentials:"include",signal:controller.signal})
      .then(async(response)=>{const body=await response.json();if(!response.ok)throw new Error(body.detail||"看板加载失败");return body as Metrics;})
      .then(setData).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return ()=>controller.abort();
  },[days,revision]);
  const visible=data && !loading && !error ? data : null;
  function option(series:EChartsCoreOption["series"]): EChartsCoreOption {
    return {animation:false,aria:{enabled:true},color:["#a52238","#d6a74b","#6d907f"],tooltip:{trigger:"axis",confine:true},legend:{top:0,textStyle:{color:"#75685c"}},grid:{left:60,right:20,top:40,bottom:32},xAxis:{type:"category",data:visible?.daily.map(d=>d.date.slice(5)),axisLine:{lineStyle:{color:"#e5d8c6"}},axisLabel:{color:"#8e8276"}},yAxis:{type:"value",minInterval:1,splitLine:{lineStyle:{color:"#eee5d8"}},axisLabel:{color:"#8e8276"}},series};
  }
  const daily=visible?.daily||[];
  const tableRows=[...daily].reverse().slice((tablePage-1)*10,tablePage*10);
  return <section className="admin-dashboard" aria-label="使用看板">
    <div className="admin-dashboard-toolbar"><div><h2>使用看板</h2><p>{visible?`${visible.start} — ${visible.end}`:"每日使用情况"} · 北京时间</p></div><div className="admin-actions"><FormSelect ariaLabel="统计范围" value={days} options={[{value:"7",label:"最近 7 天"},{value:"30",label:"最近 30 天"},{value:"90",label:"最近 90 天"}]} onValueChange={value=>{setDays(value);setTablePage(1);}}/><button className="btn outline" disabled={loading} onClick={()=>setRevision(v=>v+1)}>刷新</button></div></div>
    {loading?<div className="history-empty">正在加载看板…</div>:null}{error?<div className="history-empty error" role="alert">{error}</div>:null}
    {visible?<>
      <div className="admin-metric-grid">{[["创建任务",visible.totals.tasks,"数据库登记的生成任务"],["Token 消耗",visible.totals.tokens,"已结算输入 + 输出 Token"],["发起用户",visible.totals.active_users,"发起任务或生成操作的去重用户"],["积分消耗",visible.totals.credits,"已扣除积分，不包含冻结"]].map(([label,value,note])=><article className="admin-metric" key={String(label)}><h3>{label}</h3><strong>{number(Number(value))}</strong><p>{note}</p></article>)}</div>
      <div className="admin-dashboard-charts">
        <article className="admin-chart-card"><h3>每日任务</h3><Chart label="每日创建任务和已完成任务趋势" option={option([{name:"创建任务",type:"bar",barMaxWidth:22,data:daily.map(d=>d.tasks)},{name:"已完成",type:"line",smooth:true,data:daily.map(d=>d.completed)}])}/><p>已完成任务按创建日期归组，以当前登记状态为准。</p></article>
        <article className="admin-chart-card"><h3>每日 Token 消耗</h3><Chart label="每日已结算输入和输出 Token" option={option([{name:"输入 Token",type:"bar",stack:"tokens",barMaxWidth:22,data:daily.map(d=>d.input_tokens)},{name:"输出 Token",type:"bar",stack:"tokens",barMaxWidth:22,data:daily.map(d=>d.output_tokens)}])}/><p>按结算日期统计；缓存 Token 已包含在输入中。</p></article>
        <article className="admin-chart-card"><h3>每日用户</h3><Chart label="每日发起用户与新增用户趋势" option={option([{name:"发起用户",type:"line",smooth:true,data:daily.map(d=>d.active_users)},{name:"新增用户",type:"line",smooth:true,data:daily.map(d=>d.new_users)}])}/><p>发起用户根据任务与生成操作统计，不代表登录活跃用户。</p></article>
        <article className="admin-chart-card"><h3>每日积分消耗</h3><Chart label="每日已扣除积分趋势" option={option([{name:"积分",type:"bar",barMaxWidth:22,data:daily.map(d=>d.credits)}])}/><p>已结算图片 {number(visible.totals.images)} 张 · 语音 {number(visible.totals.tts_characters)} 字符</p></article>
      </div>
      <p className="admin-dashboard-coverage">统计口径：{visible.totals.settlements} 笔已结算操作，其中 {visible.totals.settlements_with_usage} 笔含用量记录。未记录、失败或尚未结算的用量未计入 Token；历史缺失数据不作估算。</p>
      <h3>每日明细</h3><div className="admin-table-wrap"><table className="admin-table"><thead><tr>{["日期","创建任务","已完成","发起用户","新增用户","输入 Token","输出 Token","图片","语音字符","积分"].map(label=><th key={label}>{label}</th>)}</tr></thead><tbody>{tableRows.map(day=><tr key={day.date}>{[day.date,day.tasks,day.completed,day.active_users,day.new_users,day.input_tokens,day.output_tokens,day.images,day.tts_characters,day.credits].map((value,i)=><td key={i}>{typeof value==="number"?number(value):value}</td>)}</tr>)}</tbody></table></div>
      <nav className="asset-library-pagination"><button className="btn outline" disabled={tablePage===1} onClick={()=>setTablePage(v=>v-1)}>上一页</button><span>第 {tablePage} 页</span><button className="btn outline" disabled={tablePage*10>=daily.length} onClick={()=>setTablePage(v=>v+1)}>下一页</button></nav>
    </>:null}
  </section>;
}
