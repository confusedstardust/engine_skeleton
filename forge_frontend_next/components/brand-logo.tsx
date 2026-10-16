import { BrandLogo as SharedBrandLogo, type BrandLogoProps } from "@narrativeos/ui/brand-logo";
import logo from "@narrativeos/ui/logo.png";

export default function BrandLogo(props: Omit<BrandLogoProps, "src">) {
  return <SharedBrandLogo src={logo.src} {...props} />;
}
