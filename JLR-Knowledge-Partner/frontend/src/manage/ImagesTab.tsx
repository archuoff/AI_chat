import clsx from "clsx";
import {
  CircleCheck,
  Clock,
  Eye,
  EyeOff,
  Hourglass,
  LoaderCircle,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { AuthImage } from "../lib/AuthImage";
import type {
  DescribeJob,
  DocImage,
  DocImages,
  DocumentInfo,
  ImageStatus,
} from "../lib/types";

export const pictureWhere = (loc: DocImage["location"]) =>
  loc.slide
    ? `Slide ${loc.slide}`
    : loc.page
      ? `Page ${loc.page}`
      : loc.sheet
        ? `${loc.sheet}${loc.cell ? ` · ${loc.cell}` : ""}`
        : loc.section || "Document";

const STATUS: Record<ImageStatus, { label: string; dot: string }> = {
  waiting: { label: "Waiting", dot: "bg-tt-amber" },
  described: { label: "Described", dot: "bg-[#0b8f81]" },
  skipped: { label: "Skipped", dot: "bg-tt-line" },
  unsupported: { label: "Unreadable", dot: "bg-tt-slate/40" },
  failed: { label: "Failed", dot: "bg-tt-ember" },
};

const column = (img: DocImage) =>
  /^Column: (.+)$/m.exec(img.context)?.[1] ?? "";
/** Card label: inside a sheet group the sheet name is the heading, so show cell + column. */
const cardLabel = (img: DocImage) =>
  img.location.sheet
    ? [img.location.cell, column(img)].filter(Boolean).join(" · ") ||
      img.location.sheet
    : pictureWhere(img.location);

const tokens = (n: number) =>
  n >= 1000 ? `${Math.round(n / 1000)}k` : String(n);

export function ImagesTab({
  doc,
  onChanged,
}: {
  doc: DocumentInfo;
  onChanged: () => void;
}) {
  const [data, setData] = useState<DocImages | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | ImageStatus>("all");
  const [open, setOpen] = useState<DocImage | null>(null);
  const [job, setJob] = useState<DescribeJob | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.docImages(doc.doc_id).then(setData, (e: Error) => setError(e.message));
  }, [doc.doc_id]);
  useEffect(load, [load]);

  // follow a running describe job
  useEffect(() => {
    api
      .describeJob()
      .then(setJob)
      .catch(() => {});
  }, []);
  const running = job?.state === "running";
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => {
      api.describeJob().then((j) => {
        setJob(j);
        if (j.state !== "running") {
          load();
          onChanged();
        }
      });
    }, 1500);
    return () => clearInterval(t);
  }, [running, load, onChanged]);

  const shown = useMemo(
    () =>
      (data?.images ?? []).filter(
        (i) => filter === "all" || i.status === filter,
      ),
    [data, filter],
  );
  // Excel: one group per sheet; other files: a single group
  const groups = useMemo(() => {
    const m = new Map<string, DocImage[]>();
    for (const img of shown)
      m.set(img.location.sheet ?? "", [
        ...(m.get(img.location.sheet ?? "") ?? []),
        img,
      ]);
    return [...m.entries()];
  }, [shown]);

  if (error)
    return (
      <div className="rounded-xl border border-tt-ember/30 bg-[#fdf0ea] p-5 text-[13.5px] text-[#8a3510]">
        {error}
      </div>
    );
  if (!data)
    return (
      <div className="flex h-64 items-center justify-center">
        <LoaderCircle className="animate-spin text-tt-electric" />
      </div>
    );

  const c = data.counts;
  const pending = c.waiting + c.failed;
  const describe = async () => {
    const est = data.estimate;
    const cost = est.cost !== null ? ` (about ${est.cost.toFixed(2)})` : "";
    if (
      !confirm(
        `Describe ${pending} picture${pending === 1 ? "" : "s"} with ${data.vision.deployment}?\n\nEstimated ${tokens(est.input_tokens + est.output_tokens)} tokens${cost}.`,
      )
    )
      return;
    setBusy(true);
    try {
      setJob(await api.describeImages({ doc_ids: [doc.doc_id] }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const setIncluded = async (img: DocImage, included: boolean) => {
    const next = await api.setImageIncluded(img.id, included);
    setOpen(next);
    load();
    onChanged();
  };

  const filters = (
    ["all", "waiting", "described", "skipped", "unsupported", "failed"] as const
  ).filter((f) => f === "all" || c[f] > 0);

  return (
    <div className="relative flex h-full min-h-0 flex-col gap-3">
      {/* status + describe */}
      <section className="rounded-xl border border-tt-line bg-white px-5 py-4">
        {running ? (
          <div>
            <div className="flex items-center gap-3">
              <LoaderCircle
                size={18}
                className="animate-spin text-tt-electric"
              />
              <div className="flex-1 text-[13.5px] font-semibold text-tt-navy">
                Describing pictures… {job.done ?? 0} of {job.total ?? 0}
              </div>
              <button
                onClick={() => api.cancelDescribe().then(setJob)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-tt-line px-2.5 py-1.5 text-[12.5px] font-medium text-tt-slate hover:text-tt-navy"
              >
                <Square size={12} /> Stop
              </button>
            </div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-tt-mist">
              <div
                className="h-full rounded-full bg-tt-electric transition-all"
                style={{
                  width: `${((job.done ?? 0) / Math.max(job.total ?? 1, 1)) * 100}%`,
                }}
              />
            </div>
            <p className="mt-2 text-[12px] text-tt-slate">
              {tokens((job.input_tokens ?? 0) + (job.output_tokens ?? 0))}{" "}
              tokens used so far · you can leave this page, it keeps running
            </p>
          </div>
        ) : (
          <div className="flex flex-wrap items-start gap-3">
            {pending === 0 ? (
              <CircleCheck
                size={19}
                className="mt-0.5 shrink-0 text-[#0b8f81]"
              />
            ) : data.vision.enabled ? (
              <Sparkles
                size={19}
                className="mt-0.5 shrink-0 text-tt-electric"
              />
            ) : (
              <Hourglass size={19} className="mt-0.5 shrink-0 text-tt-amber" />
            )}
            <div className="min-w-0 flex-1">
              <div className="text-[14px] font-semibold text-tt-navy">
                {pending === 0
                  ? c.described
                    ? `All ${c.described} picture${c.described === 1 ? "" : "s"} described and searchable`
                    : "No pictures to describe"
                  : `${pending} picture${pending === 1 ? "" : "s"} waiting to be described`}
              </div>
              <p className="mt-0.5 text-[12.5px] text-tt-slate">
                {pending > 0 && !data.vision.enabled
                  ? "They will be described once the company Azure vision model is connected. Nothing is sent to Azure until then."
                  : pending > 0
                    ? `Uses ${data.vision.deployment}. Estimated ${tokens(data.estimate.input_tokens + data.estimate.output_tokens)} tokens${data.estimate.cost !== null ? `, about ${data.estimate.cost.toFixed(2)}` : ""}.`
                    : "Descriptions are part of the search: the assistant can find and cite these pictures."}
                {c.skipped > 0 &&
                  ` ${c.skipped} skipped (icons, logos, duplicates).`}
              </p>
              {pending > 0 && !data.vision.enabled && (
                <p className="mt-1.5 text-[12px] text-tt-slate/80">
                  Estimated{" "}
                  {tokens(
                    data.estimate.input_tokens + data.estimate.output_tokens,
                  )}{" "}
                  tokens to describe them all.
                </p>
              )}
            </div>
            {pending > 0 && (
              <button
                onClick={describe}
                disabled={!data.vision.enabled || busy}
                title={
                  data.vision.enabled
                    ? undefined
                    : "Set AZURE_OPENAI_VISION_DEPLOYMENT (company Azure resource) to switch this on"
                }
                className="inline-flex items-center gap-1.5 rounded-lg bg-tt-electric px-3.5 py-2 text-[13px] font-semibold text-white transition hover:bg-tt-electric-600 disabled:cursor-not-allowed disabled:bg-tt-line disabled:text-tt-slate"
              >
                {busy ? (
                  <LoaderCircle size={14} className="animate-spin" />
                ) : data.vision.enabled ? (
                  <Sparkles size={14} />
                ) : (
                  <Clock size={14} />
                )}
                {data.vision.enabled
                  ? `Describe ${pending}`
                  : "Waiting for vision model"}
              </button>
            )}
          </div>
        )}
        {job && (job.state === "finished" || job.state === "cancelled") && (
          <p className="mt-3 border-t border-tt-line pt-2.5 text-[12px] text-tt-slate">
            Last run {job.state === "cancelled" ? "stopped" : "finished"}:{" "}
            {job.described ?? 0} described, {job.decorative ?? 0} decorative,{" "}
            {job.failed ?? 0} failed ·{" "}
            {tokens((job.input_tokens ?? 0) + (job.output_tokens ?? 0))} tokens
          </p>
        )}
      </section>

      {/* filters */}
      <div className="flex flex-wrap items-center gap-1">
        {filters.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={clsx(
              "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[12.5px] font-medium transition",
              filter === f
                ? "bg-white text-tt-navy shadow-card ring-1 ring-tt-line"
                : "text-tt-slate hover:bg-white/70 hover:text-tt-navy",
            )}
          >
            {f !== "all" && (
              <span
                className={clsx("h-1.5 w-1.5 rounded-full", STATUS[f].dot)}
              />
            )}
            {f === "all" ? "All" : STATUS[f].label}
            <span className="text-tt-slate/60">
              {f === "all" ? c.total : c[f]}
            </span>
          </button>
        ))}
      </div>

      {/* grid */}
      <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto pr-1">
        {shown.length === 0 ? (
          <p className="py-12 text-center text-[13px] text-tt-slate">
            No pictures here.
          </p>
        ) : (
          groups.map(([sheet, imgs]) => (
            <div key={sheet} className="pb-4">
              {sheet && (
                <div className="mb-2 flex items-center gap-2 px-0.5 pt-1">
                  <span className="text-[12.5px] font-semibold text-tt-navy">
                    {sheet}
                  </span>
                  <span className="text-[12px] text-tt-slate/70">
                    {imgs.length}
                  </span>
                </div>
              )}
              <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
                {imgs.map((img) => (
                  <button
                    key={img.id}
                    onClick={() => setOpen(img)}
                    className={clsx(
                      "group overflow-hidden rounded-xl border bg-white text-left transition hover:border-tt-periwinkle hover:shadow-card",
                      open?.id === img.id
                        ? "border-tt-electric"
                        : "border-tt-line",
                    )}
                    title={img.reason || undefined}
                  >
                    <div className="relative aspect-[4/3] bg-tt-mist/60">
                      {img.status === "unsupported" ? (
                        <span className="flex h-full items-center justify-center text-[11.5px] text-tt-slate/70">
                          Can't be read
                        </span>
                      ) : (
                        <AuthImage
                          id={img.id}
                          alt={pictureWhere(img.location)}
                          className={clsx(
                            "h-full w-full object-contain p-1.5",
                            img.status === "skipped" && "opacity-45 grayscale",
                          )}
                        />
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 border-t border-tt-line px-2.5 py-1.5">
                      <span
                        className={clsx(
                          "h-1.5 w-1.5 shrink-0 rounded-full",
                          STATUS[img.status].dot,
                        )}
                      />
                      <span
                        className="truncate text-[11.5px] text-tt-slate"
                        title={cardLabel(img)}
                      >
                        {cardLabel(img)}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ))
        )}
      </div>

      {/* detail */}
      {open && (
        <>
          <div
            className="fixed inset-0 z-40 bg-tt-midnight/50"
            onClick={() => setOpen(null)}
          />
          <div className="fixed inset-x-3 top-[5vh] z-50 mx-auto flex max-h-[90vh] max-w-4xl flex-col overflow-hidden rounded-2xl bg-white shadow-lift">
            <div className="flex items-center gap-3 border-b border-tt-line px-5 py-3">
              <span
                className={clsx(
                  "h-2 w-2 rounded-full",
                  STATUS[open.status].dot,
                )}
              />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[14px] font-semibold text-tt-navy">
                  {pictureWhere(open.location)}
                </div>
                <div className="text-[12px] text-tt-slate">
                  {STATUS[open.status].label}
                  {open.reason && ` · ${open.reason}`} · {open.width}×
                  {open.height}px
                </div>
              </div>
              {(open.status === "waiting" || open.status === "failed") && (
                <button
                  onClick={() => setIncluded(open, false)}
                  className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12.5px] font-medium text-tt-slate hover:bg-[#fdf0ea] hover:text-[#8a3510]"
                >
                  <EyeOff size={14} /> Skip this picture
                </button>
              )}
              {open.status === "skipped" && (
                <button
                  onClick={() => setIncluded(open, true)}
                  className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12.5px] font-medium text-tt-electric hover:bg-tt-electric/[0.06]"
                >
                  <Eye size={14} /> Include for describing
                </button>
              )}
              <button
                onClick={() => setOpen(null)}
                className="rounded-lg p-1.5 text-tt-slate hover:bg-tt-mist"
                aria-label="Close picture"
              >
                <X size={18} />
              </button>
            </div>
            <div className="grid min-h-0 flex-1 overflow-y-auto md:grid-cols-[1.4fr_1fr]">
              <div className="flex items-center justify-center bg-tt-mist/60 p-4">
                {open.status !== "unsupported" && (
                  <AuthImage
                    id={open.id}
                    thumb={false}
                    alt={pictureWhere(open.location)}
                    className="max-h-[70vh] w-auto max-w-full object-contain"
                  />
                )}
              </div>
              <div className="space-y-4 p-5 text-[13px]">
                <div>
                  <div className="text-[11.5px] font-semibold text-tt-slate">
                    Description
                  </div>
                  <p className="mt-1 whitespace-pre-line text-tt-ink">
                    {open.description || (
                      <span className="text-tt-slate/80">
                        Not described yet
                        {open.status === "waiting"
                          ? ": waiting for the vision model."
                          : "."}
                      </span>
                    )}
                  </p>
                </div>
                {open.context && (
                  <div>
                    <div className="text-[11.5px] font-semibold text-tt-slate">
                      Around it in the document
                    </div>
                    <p className="mt-1 max-h-60 overflow-y-auto whitespace-pre-line text-tt-slate">
                      {open.context}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
