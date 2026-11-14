import { BrandLogo as SharedBrandLogo, type BrandLogoProps } from "@narrativeos/ui/brand-logo";
import logo from "../app/icon.png";

export default function BrandLogo(props: Omit<BrandLogoProps, "src">) {
  return <SharedBrandLogo src={logo.src} {...props} />;
}
