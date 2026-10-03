import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: "NFC"
    property var n: bridge.nfcInfo()
    property int testTarget: 0          // taps wanted by the running test, 0 = no test
    property double testStart: 0
    readonly property var events: bridge.nfcEvents
    readonly property var testEvents: events.filter(e => e.stamp >= testStart)
    readonly property bool testing: testTarget > 0 && testEvents.length < testTarget

    // while this page is open the tags are shown here and no desktop notification is made
    onVisibleChanged: bridge.nfcWindow(visible)
    Component.onCompleted: bridge.nfcWindow(true)
    Component.onDestruction: bridge.nfcWindow(false)
    Timer { interval: 4000; repeat: true; running: page.visible; onTriggered: page.n = bridge.nfcInfo() }

    function stats(key) {
        const v = testEvents.map(e => e[key]).filter(x => x >= 0)
        if (v.length === 0) return "-"
        return Math.min(...v) + " / " + Math.round(v.reduce((a, b) => a + b, 0) / v.length) + " / " + Math.max(...v) + " ms"
    }

    ColumnLayout {
        Kirigami.Heading { level: 2; text: page.title }
        spacing: Kirigami.Units.largeSpacing

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: true
            type: n.device && n.daemon === "active" ? Kirigami.MessageType.Positive : Kirigami.MessageType.Warning
            text: !n.device ? "NFC chip not found: the nxp_nci modules are not loaded for this kernel."
                  : n.daemon !== "active" ? "NFC chip found but the reader service is " + n.daemon + "."
                  : "NFC reader ready. Touch a tag to the back of the tablet, at the right corner of the screen. While this page is open, tags show up here instead of as desktop notifications."
        }

        Kirigami.Heading { level: 3; text: "Last tag"; visible: events.length > 0 }
        Kirigami.AbstractCard {
            Layout.fillWidth: true
            visible: events.length > 0
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                QQC2.Label { text: events.length > 0 ? events[0].lines.join("\n") : ""; font.bold: true; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Kirigami.FormLayout {
                    Layout.fillWidth: true
                    QQC2.Label { Kirigami.FormData.label: "Type:"; text: events.length > 0 ? events[0].type : "" }
                    QQC2.Label { Kirigami.FormData.label: "UID:"; text: events.length > 0 ? events[0].uid : "" }
                    QQC2.Label { Kirigami.FormData.label: "Time:"; text: events.length > 0 ? events[0].time : "" }
                    QQC2.Label { Kirigami.FormData.label: "Read from the tag in:"; text: events.length > 0 && events[0].readMs >= 0 ? events[0].readMs + " ms" : "n/a" }
                    QQC2.Label { Kirigami.FormData.label: "Delivered to this window in:"; text: events.length > 0 ? events[0].deliverMs + " ms" : "" }
                }
            }
        }

        RowLayout { Kirigami.Heading { level: 3; text: "Reader test" } }
        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            opacity: 0.7
            text: "Touch the same tag several times, lifting it each time. The test shows how fast and how reliably it is read: minimum / average / maximum of the time to read the tag and of the time to reach this window."
        }
        RowLayout {
            QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                text: page.testing ? "Stop test" : "Start test (10 taps)"
                icon.name: page.testing ? "media-playback-stop" : "media-playback-start"
                onClicked: {
                    if (page.testing) { page.testTarget = 0 }
                    else { page.testStart = Date.now() / 1000; page.testTarget = 10 }
                }
            }
            QQC2.Label {
                visible: page.testTarget > 0
                text: page.testEvents.length + " / " + page.testTarget + " taps" + (page.testing ? "" : " - done")
            }
        }
        Kirigami.FormLayout {
            Layout.fillWidth: true
            visible: page.testTarget > 0 && page.testEvents.length > 0
            QQC2.Label { Kirigami.FormData.label: "Tag read (min / avg / max):"; text: page.stats("readMs") }
            QQC2.Label { Kirigami.FormData.label: "Delivery (min / avg / max):"; text: page.stats("deliverMs") }
            QQC2.Label {
                Kirigami.FormData.label: "Different tags seen:"
                text: { const s = {}; page.testEvents.forEach(e => s[e.uid] = 1); return Object.keys(s).length }
            }
        }

        RowLayout {
            Kirigami.Heading { level: 3; text: "History"; Layout.fillWidth: true }
            QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Clear"; icon.name: "edit-clear-all"; visible: events.length > 0; onClicked: bridge.clearNfcEvents() }
        }
        QQC2.Label { visible: events.length === 0; opacity: 0.6; text: "Nothing yet."; Layout.fillWidth: true }
        Repeater {
            model: events
            delegate: QQC2.ItemDelegate {
                Layout.fillWidth: true
                contentItem: ColumnLayout {
                    spacing: 0
                    QQC2.Label { text: modelData.time + "  " + modelData.type + "  " + modelData.uid; font.bold: true }
                    QQC2.Label { text: modelData.lines.join("\n"); opacity: 0.8; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                }
            }
        }

        Kirigami.FormLayout {
            Layout.fillWidth: true
            Kirigami.Separator { Kirigami.FormData.isSection: true; Kirigami.FormData.label: "Status" }
            QQC2.Label { Kirigami.FormData.label: "Chip:"; text: n.device ? "present" : "missing" }
            QQC2.Label { Kirigami.FormData.label: "Reader service (root):"; text: n.daemon }
            QQC2.Label { Kirigami.FormData.label: "Notifications (your session):"; text: n.notifier }
            QQC2.Label { Kirigami.FormData.label: "This window listening:"; text: bridge.nfcConnected ? "yes" : "no" }
        }
        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            opacity: 0.6
            text: "A link on a tag is never opened by itself: the desktop notification has an Open button. Leaving this page brings the notifications back."
        }
    }
}
