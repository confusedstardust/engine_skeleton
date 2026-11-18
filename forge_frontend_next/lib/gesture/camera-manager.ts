export class CameraManager {
  private stream: MediaStream | null = null;
  private video: HTMLVideoElement | null = null;
  async start(): Promise<HTMLVideoElement> {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new Error("手势控制需要 HTTPS 和支持摄像头的浏览器");
    this.stop();
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: {facingMode:"user",width:{ideal:640},height:{ideal:480},frameRate:{ideal:24,max:30}},
        audio: false
      });
    } catch (error) {
      if (error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "PermissionDeniedError")) {
        throw new Error("摄像头权限被拒绝，请在浏览器设置中允许访问");
      }
      throw new Error("无法打开摄像头，请检查设备是否已被其他应用占用");
    }
    this.stream = stream;
    const video = document.createElement("video");
    video.muted = true; video.autoplay = true; video.playsInline = true;
    video.srcObject = stream;
    this.video = video;
    try { await video.play(); } catch {
      this.stop(); throw new Error("摄像头已授权，但浏览器无法启动视频");
    }
    return video;
  }
  stop() {
    this.stream?.getTracks().forEach(track => track.stop());
    this.stream = null;
    if (this.video) { this.video.pause(); this.video.srcObject = null; this.video = null; }
  }
}
