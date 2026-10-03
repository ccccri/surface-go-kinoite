import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: "Audio"
    property var a: bridge.audioInfo()
    property var eqs: bridge.eqState()
    property var micList: bridge.micPresets()
    property int drag: 0
    property string editOutput: "speaker"
    readonly property bool showHints: false
    property bool advanced: bridge.uiSetting("audioAdvanced", false)
    Timer { interval: 1500; repeat: true; running: page.visible && page.drag === 0 && bridge.testState === "idle"; onTriggered: { page.a = bridge.audioInfo(); page.eqs = bridge.eqState() } }
    Connections { target: bridge; function onAudioChanged() { page.a = bridge.audioInfo(); page.eqs = bridge.eqState(); page.micList = bridge.micPresets() } function onEqChanged() { page.eqs = bridge.eqState() } }
    Component.onCompleted: bridge.osdHold(true)
    Component.onDestruction: { bridge.stopTest(); bridge.osdHold(false) }

    component Card: Rectangle {
        id: card
        property string heading
        default property alias content: body.data
        Layout.fillWidth: true
        implicitHeight: col.implicitHeight + Kirigami.Units.largeSpacing * 2
        radius: 8
        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.045)
        ColumnLayout {
            id: col
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: Kirigami.Units.largeSpacing }
            spacing: Kirigami.Units.smallSpacing
            RowLayout {
                Rectangle { width: 3; height: Kirigami.Units.gridUnit * 1.2; radius: 2; color: Kirigami.Theme.highlightColor }
                QQC2.Label { text: card.heading; font.bold: true; font.pointSize: Kirigami.Theme.defaultFont.pointSize + 2 }
            }
            ColumnLayout { id: body; Layout.fillWidth: true; spacing: Kirigami.Units.smallSpacing }
        }
    }
    component Tip: QQC2.Label {
        visible: page.showHints
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        opacity: 0.6
        font.pointSize: Kirigami.Theme.defaultFont.pointSize - 1
    }
    component Volume: ColumnLayout {
        id: dev
        property string kind
        property var info
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing
        RowLayout {
            Layout.fillWidth: true
            QQC2.Label { text: dev.info.name; opacity: 0.7; Layout.fillWidth: true }
        }
        RowLayout {
            Layout.fillWidth: true
            QQC2.ToolButton { QQC2.ToolTip.text: "Mute or unmute"; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                icon.name: dev.info.muted ? (dev.kind === "output" ? "audio-volume-muted" : "microphone-sensitivity-muted") : (dev.kind === "output" ? "audio-volume-high" : "microphone-sensitivity-high")
                onClicked: { bridge.toggleMute(dev.kind); page.a = bridge.audioInfo() }
            }
            QQC2.Slider {
                id: vol
                Layout.fillWidth: true
                Layout.preferredHeight: Kirigami.Units.gridUnit * 2.2
                from: 0; to: 1.5; stepSize: 0.01
                value: dev.info.volume
                QQC2.ToolTip.text: dev.kind === "output" ? "System volume of the speakers or headphones. Above 100% the sound is amplified and may distort." : "Microphone input level. Raise it if people hear you too quietly; lower it if you sound distorted."
                QQC2.ToolTip.visible: hovered && !pressed
                QQC2.ToolTip.delay: 600
                onPressedChanged: page.drag += pressed ? 1 : -1
                onMoved: bridge.setVolume(dev.kind, value)
            }
            ValueField {
                from: 0; to: 150; step: 1; unit: "%"
                value: Math.round(vol.value * 100)
                onCommitted: v => { bridge.setVolume(dev.kind, v / 100); page.a = bridge.audioInfo() }
            }
        }
    }
    property string micDelName: ""
    property bool micDelBuiltin: false
    QQC2.Dialog {
        id: micDeleteDialog
        width: Kirigami.Units.gridUnit * 28
        modal: true
        anchors.centerIn: QQC2.Overlay.overlay
        title: page.micDelBuiltin ? "Delete a default preset?" : "Delete preset?"
        standardButtons: QQC2.Dialog.Yes | QQC2.Dialog.No
        contentItem: QQC2.Label {
            width: parent ? parent.width : 0
            wrapMode: Text.WordWrap
            text: page.micDelBuiltin ? "You are deleting the default preset \"" + page.micDelName + "\". The only way to get it back is to apply the patches again (run the install script); your own presets are kept." : "Delete the preset \"" + page.micDelName + "\"? This cannot be undone."
        }
        onAccepted: bridge.deleteMicPreset(page.micDelName)
    }
    property var verifyLines: []
    QQC2.Dialog {
        id: verifyDialog
        width: Kirigami.Units.gridUnit * 34
        modal: true
        anchors.centerIn: QQC2.Overlay.overlay
        title: "Are the settings applied?"
        standardButtons: QQC2.Dialog.Close
        contentItem: QQC2.Label { width: parent ? parent.width : 0; wrapMode: Text.WordWrap; text: page.verifyLines.join("\n\n") }
    }
    QQC2.Dialog {
        id: micNameDialog
        modal: true
        anchors.centerIn: QQC2.Overlay.overlay
        title: "Save the current microphone settings as a preset"
        standardButtons: QQC2.Dialog.Ok | QQC2.Dialog.Cancel
        contentItem: QQC2.TextField { id: micName; implicitWidth: Kirigami.Units.gridUnit * 18; placeholderText: "Preset name"; onAccepted: micNameDialog.accept() }
        onAccepted: { if (bridge.saveMicPreset(micName.text) !== "ok") bridge.notify("Please type a name that is not one of the built-in looks.") }
    }

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        RowLayout {
            Layout.fillWidth: true
            Kirigami.Heading { level: 2; text: page.title; Layout.fillWidth: true }
            QQC2.Switch { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Advanced"; checked: page.advanced; onToggled: { page.advanced = checked; bridge.setUiSetting("audioAdvanced", checked) } }
        }

        // ------------------------------------------------ speakers and headphones
        Card {
            heading: "Speakers and headphones"
            Volume { kind: "output"; info: page.a.output }
            QQC2.Label { text: "Playing through: " + (page.eqs.active === "headphones" ? "the headphone jack" : "the speakers"); opacity: 0.7 }
            QQC2.Switch {
                id: holdSwitch
                visible: bridge.volumeHold() !== null
                text: "Hold the volume keys to repeat"
                checked: bridge.volumeHold() === true
                onToggled: bridge.setVolumeHold(checked)
                Connections { target: bridge; function onVolumeHoldChanged() { holdSwitch.checked = bridge.volumeHold() === true } }
                QQC2.ToolTip.text: tips[text]; QQC2.ToolTip.visible: hovered; QQC2.ToolTip.delay: 500
            }

            // not enabled yet: the plain boost
            ColumnLayout {
                visible: !page.eqs.available
                Layout.fillWidth: true
                SettingSlider {
                    label: "Speaker boost"
                    desc: "How much louder than the plain volume the speakers are driven. With 120 the desktop volume at 100% sounds like 120% would on a plain speaker. Above about 150 the sound starts to distort."
                    showHints: page.showHints
                    from: 100; to: 180; step: 1; unit: "%"; defaultValue: 120
                    modelValue: page.a.speakerBoost
                    onDraggingChanged: page.drag += dragging ? 1 : -1
                    onEdited: value => bridge.setSpeakerBoost(value)
                    onResetRequested: bridge.setSpeakerBoost(120)
                }
                Tip { text: "The equalizer adds ten parametric bands with a frequency response graph, presets and import of Equalizer APO / AutoEQ files, for the speakers and the headphone jack. Enabling it restarts the sound server and the camera service for a second or two: audio and cameras in open apps will need to be reopened." }
                QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Enable the equalizer"; icon.name: "view-media-equalizer"; enabled: !bridge.busy; onClicked: bridge.enableEq() }
            }

            ColumnLayout {
                visible: page.eqs.available
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                QQC2.Switch { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                    text: "Same equalizer for speakers and headphones"
                    checked: page.eqs.sync
                    onToggled: { bridge.setEqSync(checked); if (checked) page.editOutput = "speaker" }
                }
                Tip { text: "The speakers and the headphone jack are two ports of the same sound output, so one profile can serve both. Clear this option to keep a separate profile (equalizer and boost) for each output; the matching one is applied automatically when the headphone jack is connected or disconnected, by a small background service." }
                // which output is being edited, only when they are not synced
                Rectangle {
                    visible: !page.eqs.sync
                    Layout.fillWidth: true
                    Layout.preferredHeight: Kirigami.Units.gridUnit * 2.2
                    radius: 8
                    color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.07)
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 3; spacing: 3
                        Repeater {
                            model: [{ t: "Speakers", o: "speaker" }, { t: "Headphones", o: "headphones" }]
                            delegate: Rectangle {
                                readonly property bool on: page.editOutput === modelData.o
                                Layout.fillWidth: true; Layout.fillHeight: true; radius: 6
                                color: on ? Kirigami.Theme.highlightColor : "transparent"
                                QQC2.Label { anchors.centerIn: parent; text: modelData.t; font.bold: parent.on; color: parent.on ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor }
                                MouseArea { anchors.fill: parent; onClicked: page.editOutput = modelData.o }
                            }
                        }
                    }
                }
                EqEditor { Layout.fillWidth: true; output: page.eqs.sync ? "speaker" : page.editOutput; showHints: page.showHints; advanced: page.advanced }
            }

            QQC2.Label { text: "Speaker test"; font.bold: true; topPadding: Kirigami.Units.smallSpacing }
            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                Repeater {
                    model: [{ t: "Left", k: "left", i: "go-previous" }, { t: "Right", k: "right", i: "go-next" }, { t: "Both", k: "both", i: "icons/both.svg" }, { t: "Sweep", k: "sweep", i: "icons/sweep.svg" }]
                    delegate: QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                        Layout.fillWidth: true
                        Layout.preferredHeight: Kirigami.Units.gridUnit * 2.4
                        text: modelData.t
                        icon.source: modelData.i.indexOf("/") >= 0 ? Qt.resolvedUrl(modelData.i) : ""
                        icon.name: modelData.i.indexOf("/") >= 0 ? "" : modelData.i
                        icon.color: palette.buttonText
                        highlighted: bridge.testState === "tone-" + modelData.k
                        onClicked: bridge.testState === "tone-" + modelData.k ? bridge.stopTest() : bridge.playTone(modelData.k)
                    }
                }
            }
            Tip { text: "Short sounds of the desktop theme: Left plays \"front left\" in the left speaker only, Right the same on the right, Both a chime in both; if the voice comes out of the wrong side the channels are swapped. Sweep glides from very low to very high pitch (40 Hz to 16 kHz, 8 seconds): listen for rattles, distortion and how low and high the speakers really go." }
            RowLayout {
                Layout.fillWidth: true
                QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Verify the settings are applied"; icon.name: "dialog-ok"; onClicked: { page.verifyLines = bridge.verifyAudio(); verifyDialog.open() } }
                QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; visible: page.advanced && page.eqs.available; text: "Turn the equalizer off"; icon.name: "edit-delete"; enabled: !bridge.busy; onClicked: bridge.disableEq() }
                Item { Layout.fillWidth: true }
            }
        }

        // ------------------------------------------------ microphone
        Card {
            heading: "Microphone"
            Volume { kind: "input"; info: page.a.input }

            QQC2.Label { text: "Microphone test"; font.bold: true }
            RowLayout {
                Layout.fillWidth: true
                QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                    text: bridge.testState === "recording" ? "Stop" : "Record 6 seconds"
                    icon.name: bridge.testState === "recording" ? "media-playback-stop" : "media-record"
                    onClicked: bridge.testState === "recording" ? bridge.stopTest() : bridge.micRecord()
                }
                QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                    text: bridge.testState === "playing" ? "Stop" : "Play back"
                    icon.name: bridge.testState === "playing" ? "media-playback-stop" : "media-playback-start"
                    enabled: bridge.hasRecording && bridge.testState !== "recording"
                    onClicked: bridge.testState === "playing" ? bridge.stopTest() : bridge.micPlayback()
                }
                QQC2.ProgressBar { Layout.fillWidth: true; from: 0; to: 1; value: bridge.micLevel }
            }
            Tip { text: "Say something while it records: the bar should reach the upper half without hitting the end. Play it back to hear what the other side of a call hears, with the settings below applied." }

            ColumnLayout {
                visible: !page.a.mic.available
                Layout.fillWidth: true
                Tip { text: "The microphone already has noise suppression. The enhancer adds a gain stage and a small equaliser on top of it. Enabling restarts the sound server and the camera service for a second or two: audio and cameras in open apps will need to be reopened. The settings then apply to every app." }
                QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Enable the microphone enhancer"; icon.name: "audio-input-microphone"; enabled: !bridge.busy; onClicked: bridge.enableMicEnhancer(true) }
            }
            ColumnLayout {
                visible: page.a.mic.available
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                QQC2.Label { Layout.fillWidth: true; wrapMode: Text.WordWrap; visible: !page.a.mic.running; text: "The enhancer is configured but not running yet: restart the sound server or log out and in." }

                QQC2.Label { text: "Preset"; font.bold: true }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    QQC2.ComboBox { id: micBox; Layout.fillWidth: true; model: page.micList.map(p => p.name + (p.builtin ? "" : "  (custom)")) }
                    QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Apply"; icon.name: "dialog-ok-apply"; onClicked: bridge.applyMicPreset(page.micList[micBox.currentIndex].name) }
                    QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Save as..."; icon.name: "document-save-as"; onClicked: { micName.text = ""; micNameDialog.open(); micName.forceActiveFocus() } }
                    QQC2.Button { icon.name: "edit-delete"; enabled: micBox.currentIndex >= 0 && page.micList.length > 0; onClicked: { micDelName = page.micList[micBox.currentIndex].name; micDelBuiltin = page.micList[micBox.currentIndex].builtin; micDeleteDialog.open() }
                        QQC2.ToolTip.text: "Delete the selected preset"; QQC2.ToolTip.visible: hovered }
                }

                Repeater {
                    model: [
                        { k: "gain", l: "Gain", f: -12, t: 12, s: 0.5, d: 0, u: "dB", adv: false, desc: "Makes everything louder or quieter after the filters." },
                        { k: "lowcut", l: "Low cut", f: 40, t: 300, s: 5, d: 80, u: "Hz", adv: false, desc: "Removes rumble, table knocks and wind below this pitch. Higher values thin the voice." },
                        { k: "bass", l: "Bass", f: -12, t: 12, s: 0.5, d: 0, u: "dB", adv: true, desc: "Adds or removes body below about 200 Hz. Reduce it if the voice sounds boomy close to the microphone." },
                        { k: "presence", l: "Presence", f: -6, t: 9, s: 0.5, d: 0, u: "dB", adv: true, desc: "Brings the voice forward (around 3 kHz) so words are easier to understand." },
                        { k: "treble", l: "Treble", f: -12, t: 12, s: 0.5, d: 0, u: "dB", adv: true, desc: "Adds air or takes away hiss and harsh s sounds above about 8 kHz." }
                    ]
                    delegate: SettingSlider {
                        visible: !modelData.adv || page.advanced
                        label: modelData.l
                        desc: modelData.desc
                        showHints: page.showHints
                        from: modelData.f; to: modelData.t; step: modelData.s
                        unit: modelData.u
                        defaultValue: modelData.d
                        modelValue: page.a.mic[modelData.k]
                        onDraggingChanged: page.drag += dragging ? 1 : -1
                        onEdited: value => bridge.setMicSetting(modelData.k, value)
                        onResetRequested: bridge.setMicSetting(modelData.k, modelData.d)
                    }
                }
                QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Turn the enhancer off"; icon.name: "edit-delete"; enabled: !bridge.busy; visible: page.advanced; onClicked: bridge.enableMicEnhancer(false) }
            }
        }
        Item { Layout.preferredHeight: Kirigami.Units.gridUnit * 2 }
    }
}
