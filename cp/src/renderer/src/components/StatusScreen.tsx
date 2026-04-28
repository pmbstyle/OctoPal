import { motion } from "framer-motion";

import octoImage from "../../../../assets/octo.png";

export function StatusScreen({
  title,
  body,
  octoAlt,
  busy,
}: {
  title: string;
  body: string;
  octoAlt: string;
  busy?: boolean;
}) {
  return (
    <motion.section
      className="status-screen"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -16 }}
      transition={{ duration: 0.24 }}
    >
      <img className={busy ? "octo status-octo pulse" : "octo status-octo"} src={octoImage} alt={octoAlt} />
      <h1>{title}</h1>
      <p>{body}</p>
    </motion.section>
  );
}
