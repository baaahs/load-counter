import Combine
import Foundation
import SwiftUI

struct ContentView: View {
    @StateObject private var bluetooth = BluetoothController()

    @State private var counterText = ""
    @State private var editingNumericField: NumericField?
    @State private var numericDraft = ""
    @FocusState private var focusedNumericField: NumericField?
    @State private var triggerDistanceCm = 40
    @State private var neutralMarginCm = 8
    @State private var timeoutSeconds = 20.0
    @State private var cooldownSeconds = 10.0
    @State private var brightness = 100.0
    @State private var sensorOrder = "A/B"
    @State private var debugMode = false

    @State private var showDefaultsConfirmation = false
    @State private var showCalibrationConfirmation = false
    @State private var showLearningCalibrationConfirmation = false
    @State private var showLearningSheet = false
    @State private var isFinishingLearning = false
    @State private var showMatrixControls = false

    private enum NumericField: Hashable {
        case counter
        case triggerDistance
        case neutralMargin
        case timeout
        case cooldown
        case brightness
    }

    var body: some View {
        NavigationStack {
            List {
                connectionSection
                powerSection
                    .disabled(!bluetooth.isReady)
                counterSection
                    .disabled(!controlsAreEnabled)
                historySection
                learningSection
                    .disabled(!controlsAreEnabled)
                sensorsSection
                    .disabled(!controlsAreEnabled)
                timingSection
                    .disabled(!controlsAreEnabled)
                displaySection
                    .disabled(!controlsAreEnabled)
                advancedSection
                    .disabled(!controlsAreEnabled)
                matrixMenuSection
                    .disabled(!controlsAreEnabled)
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Load Counter")
            .tint(.purple)
            .toolbar {
                if editingNumericField != nil {
                    ToolbarItemGroup(placement: .keyboard) {
                        Button("Cancel") {
                            cancelNumericEdit()
                        }

                        Spacer()

                        Button("Done") {
                            commitNumericEdit()
                        }
                        .fontWeight(.semibold)
                        .disabled(numericDraft.isEmpty)
                    }
                }
            }
            .onChange(of: bluetooth.deviceState) { _, state in
                guard let state else {
                    return
                }
                applyDeviceState(state)
                if state.learning?.active == true, !isFinishingLearning {
                    showLearningSheet = true
                } else if state.learning?.active != true, isFinishingLearning {
                    showLearningSheet = false
                    isFinishingLearning = false
                }
            }
            .onReceive(Timer.publish(every: 1, on: .main, in: .common).autoconnect()) { _ in
                if bluetooth.isReady {
                    bluetooth.refreshState()
                }
            }
            .alert("Calibrate sensors?", isPresented: $showCalibrationConfirmation) {
                Button("Cancel", role: .cancel) {}
                Button("Calibrate") {
                    bluetooth.send("calibrate", feedback: "Calibrating")
                }
            } message: {
                Text("Keep the sensors clear while calibration runs.")
            }
            .alert("Reset settings?", isPresented: $showDefaultsConfirmation) {
                Button("Cancel", role: .cancel) {}
                Button("Reset", role: .destructive) {
                    bluetooth.send("reset_defaults", feedback: "Defaults restored")
                }
            } message: {
                Text("This restores the load counter settings to defaults.")
            }
            .sheet(isPresented: $showMatrixControls, onDismiss: closeMatrixMenu) {
                matrixControlsSheet
            }
            .sheet(isPresented: $showLearningSheet) {
                learningSheet
            }
        }
    }

    private var connectionSection: some View {
        Section {
            HStack(spacing: 12) {
                Image(systemName: bluetooth.isReady ? "checkmark.circle.fill" : "antenna.radiowaves.left.and.right")
                    .font(.title2)
                    .foregroundStyle(bluetooth.isReady ? .green : .secondary)
                    .frame(width: 32)

                VStack(alignment: .leading, spacing: 3) {
                    Text(bluetooth.isReady ? "Connected" : bluetooth.stateText)
                        .font(.headline)
                    Text(connectionSubtitle)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                Button(bluetooth.isReady ? "Disconnect" : "Connect") {
                    bluetooth.isReady ? bluetooth.disconnect() : bluetooth.scan()
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
            }
            .padding(.vertical, 4)
        }
    }

    private var counterSection: some View {
        Section("Counter") {
            editableNumberRow(
                field: .counter,
                title: "Count",
                value: counterDisplayText,
                systemImage: "number"
            )

            Button {
                bluetooth.send("play_animation", feedback: "Playing animation")
            } label: {
                Label("Play Count Animation", systemImage: "play.circle")
            }
        }
    }

    private var historySection: some View {
        Section {
            NavigationLink {
                HistoryView(bluetooth: bluetooth)
            } label: {
                Label {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("History and Reports")
                        Text(historySubtitle)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                } icon: {
                    Image(systemName: "chart.xyaxis.line")
                        .foregroundStyle(.purple)
                }
            }
        }
    }

    private var powerSection: some View {
        Section {
            Toggle(isOn: loadCounterPowerBinding) {
                Label {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Load Counter")
                        Text(programStatusText)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                } icon: {
                    Image(systemName: isProgramRunning ? "power.circle.fill" : "power.circle")
                }
            }
        }
    }

    private var learningSection: some View {
        Section("Learn") {
            Button {
                if isLearning {
                    showLearningSheet = true
                } else {
                    isFinishingLearning = false
                    bluetooth.send("learn_start", feedback: "Learning started")
                    showLearningSheet = true
                }
            } label: {
                Label(isLearning ? "Open Learning Session" : "Start Learning", systemImage: "graduationcap")
                    .foregroundStyle(.purple)
            }

            if isLearning, let learning = bluetooth.deviceState?.learning {
                LabeledContent("Events", value: "\(learning.eventCount)")
            }
        }
    }

    private var learningSheet: some View {
        NavigationStack {
            Form {
                if isFinishingLearning {
                    Section {
                        HStack {
                            Spacer()
                            ProgressView("Finishing learning session")
                            Spacer()
                        }
                    }
                } else if let learning = bluetooth.deviceState?.learning, learning.active {
                    Section {
                        learningParameterRow("Status", value: learningStatusText(learning), systemImage: "waveform.path.ecg")
                        learningParameterRow("Events", value: "\(learning.eventCount)", systemImage: "figure.stairs")
                    }

                    Section("Parameters") {
                        learningParameterRow(
                            "Calibration",
                            value: learningCalibrationText(learning),
                            systemImage: "scope"
                        )
                        learningParameterRow(
                            "Trigger Distance",
                            value: learning.triggerDistanceCm.map { "\($0) cm" } ?? "--",
                            systemImage: "ruler"
                        )
                        learningParameterRow(
                            "Neutral Margin",
                            value: learning.neutralMarginCm.map { "\($0) cm" } ?? "--",
                            systemImage: "dot.circle.and.hand.point.up.left.fill"
                        )
                        learningParameterRow("Timeout", value: millisecondsText(learning.timeoutMs), systemImage: "timer")
                        learningParameterRow("Cooldown", value: millisecondsText(learning.cooldownMs), systemImage: "hourglass")
                        learningParameterRow("Sensor Order", value: learning.sensorOrder ?? "--", systemImage: "arrow.left.arrow.right")
                    }

                    Section {
                        Button {
                            showLearningCalibrationConfirmation = true
                        } label: {
                            Label("Calibrate", systemImage: "dot.scope")
                        }
                        .disabled(learning.phase == "observing" || learning.phase == "calibrating")

                        Button {
                            bluetooth.send("learn_count", feedback: "Observing event")
                        } label: {
                            Label("Count", systemImage: "plus.circle.fill")
                        }
                        .disabled(learning.phase != "ready")

                        Button {
                            bluetooth.send("learn_end", feedback: "Learning saved")
                            isFinishingLearning = true
                        } label: {
                            Label("End and Save", systemImage: "checkmark.circle.fill")
                        }
                        .disabled(learning.phase == "observing" || learning.phase == "calibrating")

                        Button(role: .destructive) {
                            bluetooth.send("learn_cancel", feedback: "Learning cancelled")
                            isFinishingLearning = true
                        } label: {
                            Label("Cancel", systemImage: "xmark.circle")
                        }
                    }
                } else {
                    ProgressView()
                }
            }
            .navigationTitle("Learn")
            .navigationBarTitleDisplayMode(.inline)
            .tint(.purple)
            .interactiveDismissDisabled(isLearning || isFinishingLearning)
            .alert("Calibrate sensors?", isPresented: $showLearningCalibrationConfirmation) {
                Button("Cancel", role: .cancel) {}
                Button("Calibrate") {
                    bluetooth.send("learn_calibrate", feedback: "Calibrating")
                }
            } message: {
                Text("Keep the sensors clear. Calibration stays in this learning session until you end and save.")
            }
        }
    }

    private var sensorsSection: some View {
        Section("Sensors") {
            Picker("Order", selection: sensorOrderBinding) {
                Text("A then B").tag("A/B")
                Text("B then A").tag("B/A")
            }

            LabeledContent {
                Text(baseDistanceText)
                    .foregroundStyle(.secondary)
            } label: {
                Label("Calibration", systemImage: "scope")
            }

            Button {
                showCalibrationConfirmation = true
            } label: {
                Label("Calibrate Sensors", systemImage: "dot.scope")
            }
        }
    }

    private var timingSection: some View {
        Section("Timing") {
            editableNumberRow(
                field: .triggerDistance,
                title: "Trigger Distance",
                value: "\(triggerDistanceCm) cm",
                systemImage: "ruler"
            )

            editableNumberRow(
                field: .neutralMargin,
                title: "Neutral Margin",
                value: "\(neutralMarginCm) cm",
                systemImage: "ruler"
            )

            editableNumberRow(
                field: .timeout,
                title: "Timeout",
                value: secondsText(timeoutSeconds),
                systemImage: "timer"
            )

            editableNumberRow(
                field: .cooldown,
                title: "Cooldown",
                value: secondsText(cooldownSeconds),
                systemImage: "hourglass"
            )
        }
    }

    private var displaySection: some View {
        Section("Display") {
            VStack(alignment: .leading, spacing: 10) {
                editableNumberRow(
                    field: .brightness,
                    title: "Brightness",
                    value: "\(Int(brightness))%",
                    systemImage: "sun.max"
                )

                Slider(value: $brightness, in: 1...100, step: 1) { editing in
                    if !editing {
                        sendBrightness()
                    }
                }
            }
            .padding(.vertical, 4)

            Toggle(isOn: debugModeBinding) {
                Label("Debug Overlay", systemImage: "gauge.with.dots.needle.67percent")
            }
        }
    }

    private var advancedSection: some View {
        Section("Advanced") {
            Button(role: .destructive) {
                showDefaultsConfirmation = true
            } label: {
                Label("Reset Settings to Defaults", systemImage: "exclamationmark.arrow.triangle.2.circlepath")
                    .foregroundStyle(.red)
            }
        }
    }

    private var matrixMenuSection: some View {
        Section {
            Button {
                openMatrixMenu()
            } label: {
                Label("Open Pi Settings Menu", systemImage: "slider.horizontal.3")
                    .font(.headline)
            }
        }
    }

    private var matrixControlsSheet: some View {
        NavigationStack {
            List {
                Section("Matrix Menu") {
                    VStack(spacing: 12) {
                        matrixControlButton("Up", systemImage: "chevron.up", command: "up")

                        HStack(spacing: 12) {
                            matrixControlButton("Left", systemImage: "chevron.left", command: "left")
                            matrixControlButton("Enter", systemImage: "arrow.turn.down.left", command: "enter")
                            matrixControlButton("Right", systemImage: "chevron.right", command: "right")
                        }

                        matrixControlButton("Down", systemImage: "chevron.down", command: "down")
                    }
                    .padding(.vertical, 8)
                }

                Section {
                    Button {
                        showMatrixControls = false
                    } label: {
                        Image(systemName: "xmark")
                            .font(.title3.weight(.semibold))
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .accessibilityLabel("Esc")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.large)
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Pi Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showMatrixControls = false
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .accessibilityLabel("Done")
                    }
                }
            }
        }
        .presentationDetents([.medium])
    }

    private var sensorOrderBinding: Binding<String> {
        Binding(
            get: { sensorOrder },
            set: { newValue in
                sensorOrder = newValue
                bluetooth.send("sensor_order:\(newValue)", feedback: "Sensor order \(newValue)")
            }
        )
    }

    private var debugModeBinding: Binding<Bool> {
        Binding(
            get: { debugMode },
            set: { newValue in
                debugMode = newValue
                bluetooth.send("debug:\(newValue ? 1 : 0)", feedback: newValue ? "Debug overlay on" : "Debug overlay off")
            }
        )
    }

    private var loadCounterPowerBinding: Binding<Bool> {
        Binding(
            get: { isProgramRunning },
            set: { newValue in
                bluetooth.send(
                    newValue ? "loadcounter_start" : "loadcounter_stop",
                    feedback: newValue ? "Load Counter on" : "Load Counter off"
                )
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) {
                    bluetooth.refreshState()
                }
            }
        )
    }

    private var connectionSubtitle: String {
        if bluetooth.isReady {
            return "Ready for remote control"
        }
        return bluetooth.lastMessage
    }

    private var historySubtitle: String {
        if bluetooth.isUsingSampleHistory {
            return "Offline sample data"
        }
        if bluetooth.isLoadingHistory {
            return "Syncing from device"
        }
        if !bluetooth.historyEvents.isEmpty {
            return "\(bluetooth.historyEvents.count) events available"
        }
        if !bluetooth.isReady {
            return "Offline chart preview available"
        }
        return "Charts, stats, and PDF export"
    }

    private var counterDisplayText: String {
        if editingNumericField == .counter {
            return numericDraft.isEmpty ? "0" : numericDraft
        }
        if !counterText.isEmpty {
            return counterText
        }
        return bluetooth.isReady ? "Loading" : "--"
    }

    private var isLearning: Bool {
        bluetooth.deviceState?.learning?.active == true
    }

    private var isProgramRunning: Bool {
        bluetooth.deviceState?.program?.active ?? true
    }

    private var controlsAreEnabled: Bool {
        bluetooth.isReady && isProgramRunning
    }

    private var programStatusText: String {
        guard bluetooth.isReady else {
            return "Disconnected"
        }
        guard let program = bluetooth.deviceState?.program else {
            return "Checking"
        }
        return program.active ? "Running" : program.status.capitalized
    }

    private var baseDistanceText: String {
        guard
            let settings = bluetooth.deviceState?.settings,
            let first = settings.baseDistance1Cm,
            let second = settings.baseDistance2Cm
        else {
            return "Not calibrated"
        }

        let baseA = settings.sensorOrder == "B/A" ? second : first
        let baseB = settings.sensorOrder == "B/A" ? first : second
        return "A \(baseA) cm, B \(baseB) cm"
    }

    private func editableNumberRow(field: NumericField, title: String, value: String, systemImage: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: systemImage)
                .font(.body.weight(.medium))
                .foregroundStyle(.purple)
                .frame(width: 26, alignment: .center)

            Text(title)
                .foregroundStyle(.primary)

            Spacer()

            if editingNumericField == field {
                TextField("Value", text: $numericDraft)
                    .keyboardType(numericAllowsDecimal(field) ? .decimalPad : .numberPad)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .focused($focusedNumericField, equals: field)
                    .font(.body.weight(.semibold))
                    .monospacedDigit()
                    .multilineTextAlignment(.trailing)
                    .frame(minWidth: 64, maxWidth: 120, alignment: .trailing)
                    .onChange(of: numericDraft) { _, newValue in
                        let sanitized = sanitizedNumericText(newValue, allowsDecimal: numericAllowsDecimal(field))
                        if sanitized != newValue {
                            numericDraft = sanitized
                        }
                    }
                    .onSubmit {
                        commitNumericEdit()
                    }
                    .onAppear {
                        focusedNumericField = field
                    }

                if let unit = numericUnit(for: field) {
                    Text(unit)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text(value)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()

                Image(systemName: "chevron.right")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.tertiary)
            }
        }
        .contentShape(Rectangle())
        .onTapGesture {
            if editingNumericField != field {
                beginNumericEdit(field)
            }
        }
    }

    private func matrixControlButton(_ title: String, systemImage: String, command: String) -> some View {
        Button {
            bluetooth.send(command, feedback: title)
        } label: {
            Image(systemName: systemImage)
                .font(.title3.weight(.semibold))
                .frame(maxWidth: .infinity, minHeight: 44)
                .accessibilityLabel(title)
        }
        .buttonStyle(.bordered)
        .controlSize(.large)
    }

    private func applyDeviceState(_ state: LoadCounterDeviceState) {
        if editingNumericField != .counter {
            counterText = "\(state.counter)"
        }
        if editingNumericField != .triggerDistance {
            triggerDistanceCm = state.settings.triggerDistanceCm
        }
        if editingNumericField != .neutralMargin {
            neutralMarginCm = state.settings.neutralMarginCm
        }
        if editingNumericField != .timeout {
            timeoutSeconds = Double(state.settings.timeoutMs) / 1000
        }
        if editingNumericField != .cooldown {
            cooldownSeconds = Double(state.settings.cooldownMs) / 1000
        }
        if editingNumericField != .brightness {
            brightness = Double(state.settings.brightnessPercent)
        }
        sensorOrder = state.settings.sensorOrder
        debugMode = state.settings.debugMode
    }

    private func openMatrixMenu() {
        bluetooth.send("menu_open", feedback: "Opening matrix menu")
        showMatrixControls = true
    }

    private func closeMatrixMenu() {
        bluetooth.send("menu_cancel", feedback: "Closing matrix menu")
    }

    private func beginNumericEdit(_ field: NumericField) {
        editingNumericField = field
        switch field {
        case .counter:
            numericDraft = counterText.isEmpty ? "" : counterText
        case .triggerDistance:
            numericDraft = "\(triggerDistanceCm)"
        case .neutralMargin:
            numericDraft = "\(neutralMarginCm)"
        case .timeout:
            numericDraft = numericSecondsText(timeoutSeconds)
        case .cooldown:
            numericDraft = numericSecondsText(cooldownSeconds)
        case .brightness:
            numericDraft = "\(Int(brightness.rounded()))"
        }
        focusedNumericField = field
    }

    private func cancelNumericEdit() {
        focusedNumericField = nil
        editingNumericField = nil
        numericDraft = ""
    }

    private func commitNumericEdit() {
        guard let field = editingNumericField else {
            return
        }

        switch field {
        case .counter:
            let value = clampedInt(numericDraft, minimum: 0, maximum: 999999)
            counterText = "\(value)"
            bluetooth.send("counter:\(value)", feedback: "Count \(value)")
        case .triggerDistance:
            let value = clampedInt(numericDraft, minimum: 5, maximum: 300)
            triggerDistanceCm = value
            bluetooth.send("trigger_distance_cm:\(value)", feedback: "Trigger distance \(value) cm")
        case .neutralMargin:
            let value = clampedInt(numericDraft, minimum: 0, maximum: 300)
            neutralMarginCm = value
            bluetooth.send("neutral_margin_cm:\(value)", feedback: "Neutral margin \(value) cm")
        case .timeout:
            let value = clampedDouble(numericDraft, minimum: 0.1, maximum: 120)
            timeoutSeconds = roundedTenths(value)
            sendMilliseconds("timeout_ms", seconds: timeoutSeconds, feedback: "Timeout \(secondsText(timeoutSeconds))")
        case .cooldown:
            let value = clampedDouble(numericDraft, minimum: 0, maximum: 120)
            cooldownSeconds = roundedTenths(value)
            sendMilliseconds("cooldown_ms", seconds: cooldownSeconds, feedback: "Cooldown \(secondsText(cooldownSeconds))")
        case .brightness:
            let value = clampedInt(numericDraft, minimum: 1, maximum: 100)
            brightness = Double(value)
            bluetooth.send("brightness:\(value)", feedback: "Brightness \(value)%")
        }

        focusedNumericField = nil
        editingNumericField = nil
        numericDraft = ""
    }

    private func sanitizedNumericText(_ text: String, allowsDecimal: Bool) -> String {
        var result = ""
        var hasDecimal = false

        for character in text {
            if character.wholeNumberValue != nil {
                result.append(character)
            } else if allowsDecimal && (character == "." || character == ",") && !hasDecimal {
                result.append(".")
                hasDecimal = true
            }

            if result.count >= 7 {
                break
            }
        }

        return result
    }

    private func numericAllowsDecimal(_ field: NumericField) -> Bool {
        switch field {
        case .timeout, .cooldown:
            return true
        case .counter, .triggerDistance, .neutralMargin, .brightness:
            return false
        }
    }

    private func learningParameterRow(_ title: String, value: String, systemImage: String) -> some View {
        LabeledContent {
            Text(value)
                .monospacedDigit()
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.trailing)
        } label: {
            Label(title, systemImage: systemImage)
                .foregroundStyle(.purple)
        }
    }

    private func learningStatusText(_ learning: LoadCounterLearningState) -> String {
        switch learning.phase {
        case "observing":
            return "Observing event"
        case "calibrating":
            return "Calibrating"
        default:
            return learning.status.replacingOccurrences(of: "_", with: " ")
        }
    }

    private func learningCalibrationText(_ learning: LoadCounterLearningState) -> String {
        guard let first = learning.baseDistance1Cm, let second = learning.baseDistance2Cm else {
            return "Not calibrated"
        }
        if learning.sensorOrder == "B/A" {
            return "A \(second) cm, B \(first) cm"
        }
        return "A \(first) cm, B \(second) cm"
    }

    private func numericUnit(for field: NumericField) -> String? {
        switch field {
        case .counter:
            return nil
        case .triggerDistance, .neutralMargin:
            return "cm"
        case .timeout, .cooldown:
            return "s"
        case .brightness:
            return "%"
        }
    }

    private func sendBrightness() {
        let percent = min(max(Int(brightness.rounded()), 1), 100)
        brightness = Double(percent)
        bluetooth.send("brightness:\(percent)", feedback: "Brightness \(percent)%")
    }

    private func sendMilliseconds(_ command: String, seconds: Double, feedback: String) {
        let milliseconds = Int((seconds * 1000).rounded())
        bluetooth.send("\(command):\(milliseconds)", feedback: feedback)
    }

    private func clampedInt(_ text: String, minimum: Int, maximum: Int) -> Int {
        let value = Int(Double(text) ?? Double(minimum))
        return min(max(value, minimum), maximum)
    }

    private func clampedDouble(_ text: String, minimum: Double, maximum: Double) -> Double {
        let value = Double(text) ?? minimum
        return min(max(value, minimum), maximum)
    }

    private func roundedTenths(_ value: Double) -> Double {
        (value * 10).rounded() / 10
    }

    private func numericSecondsText(_ seconds: Double) -> String {
        if seconds == floor(seconds) {
            return "\(Int(seconds))"
        }
        return String(format: "%.1f", seconds)
    }

    private func secondsText(_ seconds: Double) -> String {
        if seconds == floor(seconds) {
            return "\(Int(seconds)) s"
        }
        return String(format: "%.1f s", seconds)
    }

    private func millisecondsText(_ milliseconds: Int?) -> String {
        guard let milliseconds else {
            return "--"
        }
        return secondsText(Double(milliseconds) / 1000)
    }
}

#Preview {
    ContentView()
}
