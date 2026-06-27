import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import type { RouteNode, RouteResult, ConstraintState } from '@/lib/api'
import { scoreColor } from '@/lib/utils'
import { Pin, CircleX, Info } from 'lucide-react'

interface Props {
  tree: RouteNode
  routes: RouteResult[]
  gScore: number
  vScore?: number
  pinned: string[]
  blacklisted: string[]
  constraintState?: ConstraintState
  constraintHistory?: ConstraintState[]
  onNodeAction: (smiles: string, action: 'pin' | 'reject') => void
}

interface HoverTooltip {
  x: number
  y: number
  smiles: string
  imgUrl: string | null
  loading: boolean
}

interface ContextMenu {
  x: number
  y: number
  smiles: string
  isPinned: boolean
}

const NODE_R = 14
const REACTION_SIZE = 16

// Route rank colors: top route = green-ish, second = amber, third = slate
const RANK_COLORS = ['#22c55e', '#f59e0b', '#60a5fa', '#a78bfa', '#f87171']

function rankColor(rank: number | undefined): string {
  if (!rank) return '#52525b'
  return RANK_COLORS[(rank - 1) % RANK_COLORS.length]
}

function nodeStrokeColor(d: any, pinned: string[], blacklisted: string[]): string {
  const smi: string = d.data.smiles
  const status: string = d.data.node_status ?? 'accepted'
  if (blacklisted.includes(smi) || status === 'rejected') return '#ef4444'
  if (pinned.includes(smi)) return '#22c55e'
  if (status === 'repaired') return '#7c3aed'
  if (status === 'target') return scoreColor(d.data.c_score ?? 0.7)
  const c = d.data.c_score ?? 0.6
  if (c < 0.4) return '#f59e0b'
  return scoreColor(c)
}

function nodeFill(d: any, pinned: string[], blacklisted: string[]): string {
  const smi: string = d.data.smiles
  const status: string = d.data.node_status ?? 'accepted'
  if (blacklisted.includes(smi) || status === 'rejected') return '#1a0505'
  if (pinned.includes(smi)) return '#052e16'
  if (status === 'repaired') return '#1c0f2e'
  if (status === 'target') return '#16161f'
  return '#1c1c27'
}

function linkStroke(d: any, pinned: string[], blacklisted: string[]): string {
  const targetSmi: string = d.target.data.smiles
  const status: string = d.target.data.node_status ?? 'accepted'
  if (blacklisted.includes(targetSmi) || status === 'rejected') return '#ef4444'
  if (pinned.includes(targetSmi)) return '#22c55e'
  if (status === 'repaired') return '#7c3aed'
  const c = d.target.data.c_score ?? 0.6
  if (c < 0.4) return '#f59e0b'
  return '#3f3f46'
}

// Cache for PubChem molecule images
const imgCache = new Map<string, string | 'error'>()

async function fetchMolImg(smiles: string): Promise<string | null> {
  const cached = imgCache.get(smiles)
  if (cached === 'error') return null
  if (cached) return cached

  const url = `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/${encodeURIComponent(smiles)}/PNG?record_type=2d&image_size=200x150`
  try {
    const controller = new AbortController()
    const tid = setTimeout(() => controller.abort(), 3000)
    const res = await fetch(url, { signal: controller.signal })
    clearTimeout(tid)
    if (!res.ok) { imgCache.set(smiles, 'error'); return null }
    const blob = await res.blob()
    const objUrl = URL.createObjectURL(blob)
    imgCache.set(smiles, objUrl)
    return objUrl
  } catch {
    imgCache.set(smiles, 'error')
    return null
  }
}

export function SynthesisTree({
  tree, routes, gScore, vScore = 1, pinned, blacklisted,
  constraintState, constraintHistory, onNodeAction,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [menu, setMenu] = useState<ContextMenu | null>(null)
  const [tooltip, setTooltip] = useState<HoverTooltip | null>(null)
  const [showConstraints, setShowConstraints] = useState(false)

  useEffect(() => {
    if (!svgRef.current || !tree) return
    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const W = svgRef.current.clientWidth || 800
    const H = 260

    svg.attr('viewBox', `0 0 ${W} ${H}`)

    const root = d3.hierarchy<RouteNode>(tree, d => d.children ?? [])
    const totalNodes = root.descendants().length

    const treeW = Math.max(W - 80, totalNodes * 55)
    const treeH = Math.max(H - 60, (root.height + 1) * 80)
    const layout = d3.tree<RouteNode>().size([treeW, treeH]).separation((a, b) => {
      return a.parent === b.parent ? 1.2 : 1.6
    })
    layout(root as any)

    // Defs
    const defs = svg.append('defs')

    // Glow filter for target
    const glow = defs.append('filter').attr('id', 'node-glow').attr('x', '-50%').attr('y', '-50%').attr('width', '200%').attr('height', '200%')
    glow.append('feGaussianBlur').attr('stdDeviation', '2.5').attr('result', 'coloredBlur')
    const feMerge = glow.append('feMerge')
    feMerge.append('feMergeNode').attr('in', 'coloredBlur')
    feMerge.append('feMergeNode').attr('in', 'SourceGraphic')

    // Violet glow for repaired
    const repairGlow = defs.append('filter').attr('id', 'repair-glow').attr('x', '-50%').attr('y', '-50%').attr('width', '200%').attr('height', '200%')
    repairGlow.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'coloredBlur')
    const feMerge2 = repairGlow.append('feMerge')
    feMerge2.append('feMergeNode').attr('in', 'coloredBlur')
    feMerge2.append('feMergeNode').attr('in', 'SourceGraphic')

    // Zoom + pan
    const zoomG = svg.append('g')
    svg.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.25, 3])
        .on('zoom', (ev) => zoomG.attr('transform', ev.transform))
        .filter(event => !event.button && !(event.type === 'mousedown'))
    )

    const g = zoomG.append('g').attr('transform', `translate(${(W - treeW) / 2 + 40}, 36)`)

    const linkGen = d3.linkVertical<any, any>().x((d: any) => d.x).y((d: any) => d.y)

    // Links
    g.selectAll('.link')
      .data((root as any).links())
      .enter()
      .append('path')
      .attr('class', 'link')
      .attr('d', linkGen)
      .attr('fill', 'none')
      .attr('stroke', (d: any) => linkStroke(d, pinned, blacklisted))
      .attr('stroke-width', (d: any) => {
        if (pinned.includes(d.target.data.smiles)) return 2
        if (d.target.data.node_status === 'repaired') return 1.5
        return 1.5
      })
      .attr('stroke-dasharray', (d: any) => {
        const status = d.target.data.node_status
        if (blacklisted.includes(d.target.data.smiles) || status === 'rejected') return '4,4'
        if (status === 'repaired') return '6,2'
        return 'none'
      })
      .style('opacity', 0)
      .transition()
      .duration(500)
      .delay((_: any, i: number) => i * 60)
      .style('opacity', 1)

    // Constraint reduction labels on links (edge annotation)
    if (constraintHistory && constraintHistory.length > 1) {
      const links = (root as any).links()
      g.selectAll('.constraint-label')
        .data(links)
        .enter()
        .append('text')
        .attr('class', 'constraint-label')
        .attr('x', (d: any) => (d.source.x + d.target.x) / 2)
        .attr('y', (d: any) => (d.source.y + d.target.y) / 2 - 4)
        .attr('text-anchor', 'middle')
        .attr('font-size', '8px')
        .attr('fill', '#52525b')
        .text((d: any) => {
          const depth = d.target.depth
          if (depth < 1 || depth > constraintHistory.length) return ''
          const curr = constraintHistory[depth - 1]
          const prev = constraintHistory[depth - 2]
          if (!curr || !prev) return ''
          const delta = curr.rxn_types.length - prev.rxn_types.length
          if (delta >= 0) return ''
          return `−${Math.abs(delta)} rxn`
        })
        .style('opacity', 0)
        .transition()
        .delay(800)
        .duration(400)
        .style('opacity', (d: any) => {
          const depth = d.target.depth
          const curr = constraintHistory[depth - 1]
          const prev = constraintHistory[depth - 2]
          if (!curr || !prev) return 0
          return curr.rxn_types.length < prev.rxn_types.length ? 1 : 0
        })
    }

    // Nodes
    const nodes = g.selectAll('.node')
      .data((root as any).descendants())
      .enter()
      .append('g')
      .attr('class', 'node')
      .attr('transform', (d: any) => `translate(${d.x},${d.y})`)
      .style('cursor', 'pointer')

    // ── Molecule nodes ──
    const molNodes = nodes.filter((d: any) => d.data.type !== 'reaction')

    // Confidence halo (outer ring — animates for low confidence)
    molNodes.append('circle')
      .attr('class', (d: any) => {
        const c = d.data.c_score ?? 0.6
        const status = d.data.node_status ?? 'accepted'
        if (status === 'rejected') return ''
        return c < 0.4 && status !== 'target' ? 'halo confidence-low' : 'halo'
      })
      .attr('r', NODE_R + 5)
      .attr('fill', 'none')
      .attr('stroke', (d: any) => {
        const status = d.data.node_status ?? 'accepted'
        if (status === 'rejected') return 'transparent'
        if (status === 'repaired') return '#7c3aed'
        if (status === 'target') return '#7c3aed'
        const c = d.data.c_score ?? 0.6
        return c < 0.4 ? '#f59e0b' : scoreColor(c)
      })
      .attr('stroke-width', (d: any) => d.data.node_status === 'target' ? 1.5 : 1)
      .attr('stroke-dasharray', (d: any) => {
        const status = d.data.node_status ?? 'accepted'
        if (status === 'repaired') return '5,2'
        if (status === 'target') return 'none'
        return '3,2'
      })
      .attr('opacity', (d: any) => {
        const status = d.data.node_status ?? 'accepted'
        if (status === 'rejected') return 0
        if (status === 'target') return 0.6
        return 0.4
      })

    // Core circle — entrance animation
    const circles = molNodes.append('circle')
      .attr('r', 0)
      .attr('fill', (d: any) => nodeFill(d, pinned, blacklisted))
      .attr('stroke', (d: any) => nodeStrokeColor(d, pinned, blacklisted))
      .attr('stroke-width', (d: any) => d.data.node_status === 'target' ? 2.5 : 1.5)
      .attr('filter', (d: any) => {
        const status = d.data.node_status ?? 'accepted'
        if (status === 'target') return 'url(#node-glow)'
        if (status === 'repaired') return 'url(#repair-glow)'
        return 'none'
      })

    // Rejected nodes: animate in red, then fade if repair exists
    const hasRepair = routes.some(r => r.repaired)
    circles
      .transition()
      .duration(400)
      .delay((d: any, i: number) => i * 50)
      .attr('r', NODE_R)
      .on('end', function(d: any) {
        if (d.data.node_status === 'rejected' && hasRepair) {
          d3.select(this)
            .transition()
            .delay(400)
            .duration(300)
            .attr('r', 0)
            .style('opacity', 0)
        }
      })

    // Repaired nodes: delayed fade-in after rejected collapses
    molNodes.filter((d: any) => d.data.node_status === 'repaired')
      .select('circle')
      .style('opacity', 0)
      .transition()
      .delay(900)
      .duration(500)
      .style('opacity', 1)

    // Node label inside circle
    molNodes.append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'central')
      .attr('font-size', '7px')
      .attr('font-weight', '600')
      .attr('fill', (d: any) => {
        const status = d.data.node_status ?? 'accepted'
        if (status === 'rejected') return '#ef4444'
        if (status === 'repaired') return '#a78bfa'
        if (status === 'target') return scoreColor(gScore)
        return scoreColor(d.data.c_score ?? 0.5)
      })
      .attr('pointer-events', 'none')
      .text((d: any) => {
        const status = d.data.node_status ?? 'accepted'
        if (status === 'target') return 'TGT'
        if (status === 'repaired') return '⚡'
        if (status === 'rejected') return '✕'
        return `M${d.depth}`
      })

    // Route rank label (depth-1 nodes only, non-reaction)
    molNodes.filter((d: any) => d.depth === 1 && d.data.route_rank)
      .append('text')
      .attr('y', -NODE_R - 8)
      .attr('text-anchor', 'middle')
      .attr('font-size', '8px')
      .attr('font-weight', '600')
      .attr('fill', (d: any) => rankColor(d.data.route_rank))
      .attr('pointer-events', 'none')
      .text((d: any) => `Route ${d.data.route_rank}`)

    // SMILES label below node (truncated)
    molNodes.append('text')
      .attr('y', NODE_R + 12)
      .attr('text-anchor', 'middle')
      .attr('font-size', '7px')
      .attr('fill', '#52525b')
      .attr('pointer-events', 'none')
      .text((d: any) => {
        const s: string = d.data.smiles || ''
        return s.length > 14 ? s.slice(0, 12) + '…' : s
      })

    // HT badge dot (top-right corner of node)
    molNodes.filter((d: any) => d.data.ht_type)
      .append('circle')
      .attr('cx', NODE_R - 3)
      .attr('cy', -NODE_R + 3)
      .attr('r', 4)
      .attr('fill', (d: any) => {
        const ht = d.data.ht_type as string
        if (ht.includes('01') || ht.includes('02')) return '#ef4444'
        if (ht.includes('03')) return '#f59e0b'
        return '#f97316'
      })
      .attr('stroke', '#09090b')
      .attr('stroke-width', 1)

    // Tooltip title
    molNodes.append('title')
      .text((d: any) => {
        const smi: string = d.data.smiles || ''
        const status = d.data.node_status ?? 'accepted'
        const c = d.data.c_score
        const ht = d.data.ht_type
        const rank = d.data.route_rank
        return [
          `[${status.toUpperCase()}]`,
          smi,
          c !== undefined ? `Confidence: ${(c * 100).toFixed(0)}%` : '',
          ht ? `HT: ${ht}` : '',
          rank ? `Route ${rank}` : '',
          'Right-click to pin/reject',
        ].filter(Boolean).join('\n')
      })

    // Hover: show molecular image tooltip
    molNodes
      .on('mouseenter', async (event: MouseEvent, d: any) => {
        const smi: string = d.data.smiles
        if (!smi || d.data.type === 'reaction') return
        const rect = svgRef.current!.getBoundingClientRect()
        const x = event.clientX - rect.left
        const y = event.clientY - rect.top
        setTooltip({ x, y, smiles: smi, imgUrl: null, loading: true })
        const url = await fetchMolImg(smi)
        setTooltip(prev => prev?.smiles === smi ? { ...prev, imgUrl: url, loading: false } : prev)
      })
      .on('mouseleave', () => setTooltip(null))

    // Right-click context menu
    molNodes.on('contextmenu', (event: MouseEvent, d: any) => {
      event.preventDefault()
      const smi: string = d.data.smiles
      if (!smi) return
      setTooltip(null)
      const rect = svgRef.current!.getBoundingClientRect()
      setMenu({
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
        smiles: smi,
        isPinned: pinned.includes(smi),
      })
    })

    molNodes.on('click', () => setMenu(null))

    // ── Reaction nodes (diamonds) ──
    const rxnNodes = nodes.filter((d: any) => d.data.type === 'reaction')

    rxnNodes.append('polygon')
      .attr('points', `0,${-REACTION_SIZE / 2} ${REACTION_SIZE / 2},0 0,${REACTION_SIZE / 2} ${-REACTION_SIZE / 2},0`)
      .attr('fill', (d: any) => {
        const rank = d.data.route_rank
        return rank ? rankColor(rank) + '18' : '#18181b'
      })
      .attr('stroke', (d: any) => {
        const rank = d.data.route_rank
        return rank ? rankColor(rank) + '66' : '#3f3f46'
      })
      .attr('stroke-width', 1)
      .style('opacity', 0)
      .transition()
      .duration(300)
      .delay((_: any, i: number) => i * 50)
      .style('opacity', 1)

    rxnNodes.append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'central')
      .attr('font-size', '6px')
      .attr('fill', '#71717a')
      .attr('pointer-events', 'none')
      .text('rxn')

    rxnNodes.append('title').text('Reaction step')

    svg.on('click', () => { setMenu(null) })

  }, [tree, gScore, vScore, pinned, blacklisted, constraintHistory, routes])

  return (
    <div
      ref={containerRef}
      className="relative w-full bg-zinc-950 overflow-hidden"
      style={{ minHeight: 260 }}
    >
      {/* Toolbar */}
      <div className="absolute top-2 left-3 right-3 z-10 flex items-center justify-between pointer-events-none">
        <span className="rounded bg-zinc-900/80 px-2 py-1 text-[9px] text-zinc-600 backdrop-blur pointer-events-auto">
          Scroll to zoom · Right-click node to pin/reject
        </span>
        <div className="flex items-center gap-2 pointer-events-auto">
          <div className="flex items-center gap-1.5 rounded bg-zinc-900/80 px-2 py-1 backdrop-blur">
            <div className="h-2 w-2 rounded-full" style={{ background: scoreColor(gScore * (vScore ?? 1)) }} />
            <span className="text-[9px] tabular-nums text-zinc-400">
              Score {(gScore * 100).toFixed(0)}
            </span>
          </div>
          {/* Route legend */}
          {routes.length > 1 && routes.slice(0, 3).map((_, i) => (
            <div key={i} className="flex items-center gap-1 rounded bg-zinc-900/80 px-1.5 py-1 backdrop-blur">
              <div className="h-1.5 w-1.5 rounded-full" style={{ background: rankColor(i + 1) }} />
              <span className="text-[9px] text-zinc-500">R{i + 1}</span>
            </div>
          ))}
          <button
            onClick={() => setShowConstraints(x => !x)}
            className={`flex items-center gap-1 rounded px-2 py-1 text-[9px] backdrop-blur transition-colors ${showConstraints ? 'bg-violet-900/60 text-violet-300' : 'bg-zinc-900/80 text-zinc-400 hover:text-zinc-200'}`}
          >
            <Info size={10} />
            G_C^(k)
          </button>
        </div>
      </div>

      {/* Constraint overlay */}
      {showConstraints && constraintState && (
        <div className="absolute right-3 top-10 z-20 w-60 rounded-xl border border-violet-800/40 bg-zinc-900/95 p-3 shadow-xl backdrop-blur text-[10px]">
          <p className="mb-2 font-semibold uppercase tracking-widest text-violet-400 text-[9px]">
            Active Constraint Graph G_C^(k)
          </p>
          <p className="mb-1 text-zinc-600 uppercase tracking-wider text-[9px]">Reaction types ({constraintState.rxn_types.length})</p>
          <div className="mb-2 flex flex-wrap gap-1">
            {constraintState.rxn_types.slice(0, 6).map(t => (
              <span key={t} className="rounded bg-green-950/60 px-1.5 py-0.5 text-[9px] text-green-400 border border-green-800/30">
                {t.replace(/_/g, ' ')}
              </span>
            ))}
            {constraintState.rxn_types.length > 6 && (
              <span className="text-[9px] text-zinc-600">+{constraintState.rxn_types.length - 6}</span>
            )}
          </div>
          <p className="mb-1 text-zinc-600 uppercase tracking-wider text-[9px]">Solvents ({constraintState.solvents.length})</p>
          <div className="flex flex-wrap gap-1">
            {constraintState.solvents.slice(0, 5).map(s => (
              <span key={s} className="rounded bg-blue-950/60 px-1.5 py-0.5 text-[9px] text-blue-400 border border-blue-800/30">
                {s}
              </span>
            ))}
            {constraintState.solvents.length > 5 && (
              <span className="text-[9px] text-zinc-600">+{constraintState.solvents.length - 5}</span>
            )}
          </div>
          {constraintState.excluded_count > 0 && (
            <p className="mt-2 text-[9px] text-red-500">{constraintState.excluded_count} excluded SMILES</p>
          )}
        </div>
      )}

      <svg ref={svgRef} className="w-full" style={{ height: 260 }} />

      {/* Molecule hover tooltip */}
      {tooltip && (
        <div
          className="pointer-events-none absolute z-30 rounded-xl border border-zinc-700 bg-zinc-900/98 p-2 shadow-2xl backdrop-blur"
          style={{ left: Math.min(tooltip.x + 16, (containerRef.current?.clientWidth ?? 800) - 220), top: Math.max(tooltip.y - 80, 8) }}
        >
          {tooltip.loading ? (
            <div className="flex h-[100px] w-[180px] items-center justify-center text-[10px] text-zinc-600">
              Loading structure…
            </div>
          ) : tooltip.imgUrl ? (
            <>
              <img src={tooltip.imgUrl} alt="structure" className="h-[100px] w-[180px] rounded object-contain bg-white/5" />
              <p className="mt-1 text-center text-[8px] text-zinc-700">Structure via PubChem</p>
            </>
          ) : (
            <div className="w-[180px] px-2 py-3">
              <code className="text-[9px] text-zinc-400 font-mono break-all">{tooltip.smiles}</code>
            </div>
          )}
        </div>
      )}

      {/* Context menu */}
      {menu && (
        <div
          className="absolute z-30 min-w-[160px] rounded-xl border border-zinc-700 bg-zinc-900 py-1 shadow-2xl"
          style={{ left: menu.x, top: menu.y }}
        >
          <div className="border-b border-zinc-800 px-3 py-2">
            <p className="text-[9px] text-zinc-600">Node</p>
            <p className="max-w-[140px] truncate font-mono text-[10px] text-zinc-300">{menu.smiles}</p>
          </div>
          <button
            className="flex w-full items-center gap-2 px-3 py-2 text-xs text-green-400 hover:bg-zinc-800 transition-colors"
            onClick={() => { onNodeAction(menu.smiles, 'pin'); setMenu(null) }}
          >
            <Pin size={12} />
            {menu.isPinned ? 'Unpin' : 'Pin intermediate'}
          </button>
          <button
            className="flex w-full items-center gap-2 px-3 py-2 text-xs text-red-400 hover:bg-zinc-800 transition-colors"
            onClick={() => { onNodeAction(menu.smiles, 'reject'); setMenu(null) }}
          >
            <CircleX size={12} />
            Reject (branch repair)
          </button>
        </div>
      )}
    </div>
  )
}
