import SwiftUI
import UIKit

struct ExportedHistoryReport: Identifiable {
    let url: URL
    var id: URL { url }
}

struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

enum HistoryPDFExporter {
    private static let pageRect = CGRect(x: 0, y: 0, width: 612, height: 792)
    private static let margin: CGFloat = 44
    private static let purple = UIColor(red: 0.47, green: 0.20, blue: 0.78, alpha: 1)
    private static let indigo = UIColor(red: 0.25, green: 0.30, blue: 0.74, alpha: 1)
    private static let green = UIColor(red: 0.12, green: 0.62, blue: 0.36, alpha: 1)
    private static let red = UIColor(red: 0.84, green: 0.20, blue: 0.23, alpha: 1)
    private static let blue = UIColor(red: 0.15, green: 0.43, blue: 0.84, alpha: 1)
    private static let ink = UIColor(red: 0.10, green: 0.10, blue: 0.12, alpha: 1)
    private static let secondaryInk = UIColor(red: 0.40, green: 0.40, blue: 0.44, alpha: 1)
    private static let pale = UIColor(red: 0.96, green: 0.96, blue: 0.98, alpha: 1)

    static func create(
        events: [LoadCounterHistoryEvent],
        buckets: [HistoryBucket],
        statistics: HistoryStatistics,
        range: HistoryRange,
        grouping: HistoryGrouping,
        chartStyle: HistoryChartStyle,
        valueMode: HistoryValueMode
    ) throws -> URL {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd-HHmm"
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("LoadCounter-History-\(formatter.string(from: Date())).pdf")
        let renderer = UIGraphicsPDFRenderer(bounds: pageRect)

        try renderer.writePDF(to: url) { context in
            drawDashboardPage(
                context: context,
                events: events,
                buckets: buckets,
                statistics: statistics,
                range: range,
                grouping: grouping,
                chartStyle: chartStyle,
                valueMode: valueMode
            )
            drawEventPages(context: context, events: events)
        }
        return url
    }

    private static func drawDashboardPage(
        context: UIGraphicsPDFRendererContext,
        events: [LoadCounterHistoryEvent],
        buckets: [HistoryBucket],
        statistics: HistoryStatistics,
        range: HistoryRange,
        grouping: HistoryGrouping,
        chartStyle: HistoryChartStyle,
        valueMode: HistoryValueMode
    ) {
        context.beginPage()
        let cg = context.cgContext
        cg.setFillColor(UIColor.white.cgColor)
        cg.fill(pageRect)
        cg.setFillColor(purple.cgColor)
        cg.fill(CGRect(x: 0, y: 0, width: pageRect.width, height: 10))

        drawText("LoadCounter History", in: CGRect(x: margin, y: 38, width: 420, height: 34), font: .systemFont(ofSize: 27, weight: .bold), color: ink)
        drawText(
            "\(range.rawValue) · \(grouping.rawValue) · \(valueMode.rawValue) · Generated \(Date().formatted(date: .abbreviated, time: .shortened))",
            in: CGRect(x: margin, y: 76, width: 520, height: 20),
            font: .systemFont(ofSize: 11, weight: .regular),
            color: secondaryInk
        )

        let tileWidth = (pageRect.width - margin * 2 - 12) / 2
        drawStatTile(title: "CURRENT COUNT", value: statistics.currentCount.map(String.init) ?? "--", color: purple, rect: CGRect(x: margin, y: 116, width: tileWidth, height: 70))
        drawStatTile(title: "AUTOMATIC COUNTS", value: "\(statistics.automaticCounts)", color: green, rect: CGRect(x: margin + tileWidth + 12, y: 116, width: tileWidth, height: 70))
        drawStatTile(title: "MANUAL CHANGES", value: "\(statistics.manualChanges)", color: blue, rect: CGRect(x: margin, y: 198, width: tileWidth, height: 70))
        drawStatTile(title: "RESETS", value: "\(statistics.resets)", color: red, rect: CGRect(x: margin + tileWidth + 12, y: 198, width: tileWidth, height: 70))

        let activityTitle = valueMode == .cumulative ? "Cumulative Activity" : "Activity per Interval"
        drawText(activityTitle, in: CGRect(x: margin, y: 294, width: 260, height: 24), font: .systemFont(ofSize: 17, weight: .semibold), color: ink)
        drawBucketChart(buckets, style: chartStyle, color: purple, rect: CGRect(x: margin, y: 326, width: pageRect.width - margin * 2, height: 155), context: cg)

        if valueMode == .cumulative {
            drawText("Counter Value", in: CGRect(x: margin, y: 510, width: 260, height: 24), font: .systemFont(ofSize: 17, weight: .semibold), color: ink)
            drawCounterChart(HistoryAnalytics.counterSeries(events), rect: CGRect(x: margin, y: 542, width: pageRect.width - margin * 2, height: 155), context: cg)
        } else {
            drawText("Counter Change", in: CGRect(x: margin, y: 510, width: 260, height: 24), font: .systemFont(ofSize: 17, weight: .semibold), color: ink)
            drawBucketChart(
                HistoryAnalytics.counterChangeBuckets(for: events, grouping: grouping),
                style: chartStyle,
                color: indigo,
                rect: CGRect(x: margin, y: 542, width: pageRect.width - margin * 2, height: 155),
                context: cg
            )
        }

        let peakText: String
        if let peak = statistics.busiestBucket {
            peakText = "Peak interval: \(peak.count) automatic counts on \(peak.date.formatted(date: .abbreviated, time: .shortened))"
        } else {
            peakText = "No automatic count activity in this selection"
        }
        drawText(peakText, in: CGRect(x: margin, y: 718, width: 500, height: 18), font: .systemFont(ofSize: 10, weight: .medium), color: secondaryInk)
        drawFooter(page: 1)
    }

    private static func drawEventPages(context: UIGraphicsPDFRendererContext, events: [LoadCounterHistoryEvent]) {
        let newestFirst = Array(events.sorted { $0.date > $1.date })
        let rowsPerPage = 24
        guard !newestFirst.isEmpty else { return }

        for pageStart in stride(from: 0, to: newestFirst.count, by: rowsPerPage) {
            context.beginPage()
            context.cgContext.setFillColor(UIColor.white.cgColor)
            context.cgContext.fill(pageRect)
            context.cgContext.setFillColor(purple.cgColor)
            context.cgContext.fill(CGRect(x: 0, y: 0, width: pageRect.width, height: 6))

            drawText("Event Detail", in: CGRect(x: margin, y: 30, width: 300, height: 30), font: .systemFont(ofSize: 23, weight: .bold), color: ink)
            drawText("Newest first", in: CGRect(x: margin, y: 64, width: 200, height: 18), font: .systemFont(ofSize: 10), color: secondaryInk)

            let headerY: CGFloat = 96
            drawText("DATE", in: CGRect(x: margin, y: headerY, width: 140, height: 16), font: .systemFont(ofSize: 9, weight: .bold), color: secondaryInk)
            drawText("EVENT", in: CGRect(x: 190, y: headerY, width: 180, height: 16), font: .systemFont(ofSize: 9, weight: .bold), color: secondaryInk)
            drawText("SOURCE", in: CGRect(x: 384, y: headerY, width: 90, height: 16), font: .systemFont(ofSize: 9, weight: .bold), color: secondaryInk)
            drawText("COUNT", in: CGRect(x: 490, y: headerY, width: 76, height: 16), font: .systemFont(ofSize: 9, weight: .bold), color: secondaryInk, alignment: .right)

            let pageEvents = newestFirst[pageStart..<min(pageStart + rowsPerPage, newestFirst.count)]
            for (index, event) in pageEvents.enumerated() {
                let y = headerY + 24 + CGFloat(index) * 25
                if index.isMultiple(of: 2) {
                    context.cgContext.setFillColor(pale.cgColor)
                    context.cgContext.fill(CGRect(x: margin - 4, y: y - 4, width: pageRect.width - margin * 2 + 8, height: 24))
                }
                drawText(event.date.formatted(date: .numeric, time: .shortened), in: CGRect(x: margin, y: y, width: 138, height: 16), font: .systemFont(ofSize: 9), color: ink)
                drawText(event.kind.title, in: CGRect(x: 190, y: y, width: 180, height: 16), font: .systemFont(ofSize: 9, weight: .medium), color: color(for: event.kind))
                drawText(event.source ?? "--", in: CGRect(x: 384, y: y, width: 90, height: 16), font: .systemFont(ofSize: 9), color: secondaryInk)
                let countText: String
                if let old = event.oldCount, let new = event.newCount {
                    countText = "\(old) → \(new)"
                } else {
                    countText = event.newCount.map(String.init) ?? "--"
                }
                drawText(countText, in: CGRect(x: 486, y: y, width: 80, height: 16), font: .monospacedDigitSystemFont(ofSize: 9, weight: .semibold), color: ink, alignment: .right)
            }
            drawFooter(page: pageStart / rowsPerPage + 2)
        }
    }

    private static func drawStatTile(title: String, value: String, color: UIColor, rect: CGRect) {
        let path = UIBezierPath(roundedRect: rect, cornerRadius: 8)
        pale.setFill()
        path.fill()
        color.setFill()
        UIBezierPath(roundedRect: CGRect(x: rect.minX, y: rect.minY, width: 5, height: rect.height), cornerRadius: 2.5).fill()
        drawText(value, in: CGRect(x: rect.minX + 18, y: rect.minY + 12, width: rect.width - 32, height: 28), font: .systemFont(ofSize: 22, weight: .bold), color: ink)
        drawText(title, in: CGRect(x: rect.minX + 18, y: rect.minY + 44, width: rect.width - 32, height: 16), font: .systemFont(ofSize: 9, weight: .semibold), color: secondaryInk)
    }

    private static func drawBucketChart(
        _ buckets: [HistoryBucket],
        style: HistoryChartStyle,
        color: UIColor,
        rect: CGRect,
        context: CGContext
    ) {
        drawChartBackground(rect, context: context)
        guard
            let minimum = buckets.map(\.count).min(),
            let maximum = buckets.map(\.count).max()
        else {
            drawEmptyChartText("No activity", rect: rect)
            return
        }
        let chart = rect.insetBy(dx: 14, dy: 14)
        let lowerBound = min(0, minimum)
        let upperBound = max(0, maximum)
        let spread = max(upperBound - lowerBound, 1)
        let yPosition: (Int) -> CGFloat = { value in
            chart.maxY - chart.height * CGFloat(value - lowerBound) / CGFloat(spread)
        }
        let zeroY = yPosition(0)
        context.setStrokeColor(secondaryInk.withAlphaComponent(0.35).cgColor)
        context.setLineWidth(0.75)
        context.move(to: CGPoint(x: chart.minX, y: zeroY))
        context.addLine(to: CGPoint(x: chart.maxX, y: zeroY))
        context.strokePath()
        let slotWidth = chart.width / CGFloat(max(buckets.count, 1))
        if style == .bars {
            for (index, bucket) in buckets.enumerated() {
                let valueY = yPosition(bucket.count)
                let width = min(24, max(2, slotWidth * 0.64))
                let bar = CGRect(
                    x: chart.minX + CGFloat(index) * slotWidth + (slotWidth - width) / 2,
                    y: min(valueY, zeroY),
                    width: width,
                    height: max(abs(zeroY - valueY), 1)
                )
                (bucket.count < 0 ? red : color).setFill()
                UIBezierPath(roundedRect: bar, cornerRadius: min(3, width / 2)).fill()
            }
        } else {
            let path = UIBezierPath()
            for (index, bucket) in buckets.enumerated() {
                let x = chart.minX + (buckets.count == 1 ? chart.width / 2 : CGFloat(index) * chart.width / CGFloat(buckets.count - 1))
                let y = yPosition(bucket.count)
                index == 0 ? path.move(to: CGPoint(x: x, y: y)) : path.addLine(to: CGPoint(x: x, y: y))
            }
            color.setStroke()
            path.lineWidth = 3
            path.lineJoinStyle = .round
            path.lineCapStyle = .round
            path.stroke()
        }
    }

    private static func drawCounterChart(_ events: [LoadCounterHistoryEvent], rect: CGRect, context: CGContext) {
        drawChartBackground(rect, context: context)
        let values = events.compactMap(\.newCount)
        guard !values.isEmpty, let minimum = values.min(), let maximum = values.max() else {
            drawEmptyChartText("No counter values", rect: rect)
            return
        }
        let chart = rect.insetBy(dx: 14, dy: 14)
        let spread = max(maximum - minimum, 1)
        let path = UIBezierPath()
        for (index, value) in values.enumerated() {
            let x = chart.minX + (values.count == 1 ? chart.width / 2 : CGFloat(index) * chart.width / CGFloat(values.count - 1))
            let y = chart.maxY - chart.height * CGFloat(value - minimum) / CGFloat(spread)
            index == 0 ? path.move(to: CGPoint(x: x, y: y)) : path.addLine(to: CGPoint(x: x, y: y))
        }
        indigo.setStroke()
        path.lineWidth = 3
        path.lineJoinStyle = .round
        path.lineCapStyle = .round
        path.stroke()
    }

    private static func drawChartBackground(_ rect: CGRect, context: CGContext) {
        context.setFillColor(pale.cgColor)
        context.fill(rect)
        context.setStrokeColor(UIColor(red: 0.87, green: 0.87, blue: 0.90, alpha: 1).cgColor)
        context.setLineWidth(0.5)
        for step in 1..<4 {
            let y = rect.minY + rect.height * CGFloat(step) / 4
            context.move(to: CGPoint(x: rect.minX, y: y))
            context.addLine(to: CGPoint(x: rect.maxX, y: y))
        }
        context.strokePath()
    }

    private static func drawEmptyChartText(_ text: String, rect: CGRect) {
        drawText(text, in: CGRect(x: rect.minX, y: rect.midY - 8, width: rect.width, height: 18), font: .systemFont(ofSize: 11), color: secondaryInk, alignment: .center)
    }

    private static func drawFooter(page: Int) {
        drawText("LoadCounter", in: CGRect(x: margin, y: 758, width: 180, height: 16), font: .systemFont(ofSize: 9, weight: .semibold), color: secondaryInk)
        drawText("Page \(page)", in: CGRect(x: 460, y: 758, width: 108, height: 16), font: .systemFont(ofSize: 9), color: secondaryInk, alignment: .right)
    }

    private static func drawText(
        _ text: String,
        in rect: CGRect,
        font: UIFont,
        color: UIColor,
        alignment: NSTextAlignment = .left
    ) {
        let paragraph = NSMutableParagraphStyle()
        paragraph.alignment = alignment
        (text as NSString).draw(
            in: rect,
            withAttributes: [
                .font: font,
                .foregroundColor: color,
                .paragraphStyle: paragraph,
            ]
        )
    }

    private static func color(for kind: HistoryEventKind) -> UIColor {
        switch kind {
        case .automatic: return green
        case .manual: return blue
        case .reset: return red
        case .learning: return purple
        case .other: return secondaryInk
        }
    }
}
