"use client";
import GestureWorkHost from "../../components/gesture/gesture-work-host";
import styles from "./practice.module.css";
export default function AnimationPreview({html,label="动画成品预览",compact=false}:{
  html:string;label?:string;compact?:boolean;
}){
  return <div className={styles.preview}><GestureWorkHost html={html} label={label} compact={compact} disclaimer/></div>;
}
