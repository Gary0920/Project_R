import projectRLogoUrl from "../assets/project-r-logo.png";

export type ProjectRLogoProps = {
  className?: string;
};

export function ProjectRLogo({ className }: ProjectRLogoProps) {
  return <img alt="Project_R" className={className ?? "project-r-logo"} src={projectRLogoUrl} />;
}
