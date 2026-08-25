import QtQuick
import QtQuick.Controls
import Quickshell
import qs.Commons
import qs.Ui
import "StatusModel.js" as StatusModel

BarWidget {
  id: root
  moduleName: "godhiraj.omaudit-status"

  property bool popupOpen: false
  property int selectedAction: 1
  property var waitingStatus: StatusModel.errorDocument("Waiting for Omaudit Status service")

  readonly property var guardService: bar?.shell?.serviceFor("godhiraj.omaudit-status")
  readonly property var hostBarConfig: bar ? bar.barConfig : null
  readonly property var statusDocument: guardService && guardService.status
    ? guardService.status : waitingStatus
  readonly property string guardState: StatusModel.state(statusDocument)
  readonly property string guardTone: StatusModel.tone(statusDocument)
  readonly property string guardSummary: StatusModel.summary(statusDocument)
  readonly property var totals: statusDocument && statusDocument.totals
    ? statusDocument.totals : StatusModel.zeroTotals()
  readonly property var visiblePlugins: StatusModel.visiblePlugins(statusDocument, 8)
  readonly property color foreground: bar ? bar.foreground : Color.popups.text
  readonly property color barForeground: bar ? bar.barForeground : Color.bar.text
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property color shieldColor: {
    var key = StatusModel.colorKey(statusDocument)
    if (key === "green") return Color.pick("omaudit-status.clean", "#6fa35b")
    if (key === "amber") return Color.pick("omaudit-status.caution", "#d0a447")
    if (key === "red") return bar ? bar.urgent : Color.urgent
    return Color.muted
  }

  function configureService() {
    var service = guardService
    if (service && typeof service.configure === "function") service.configure(settings || {})
  }

  function refresh() {
    var service = guardService
    if (service && typeof service.refresh === "function") service.refresh()
  }

  function review() {
    var service = guardService
    if (service && typeof service.review === "function") service.review()
  }

  function open() { popupOpen = true }
  function close() { popupOpen = false }
  function toggle() { popupOpen = !popupOpen }
  readonly property bool opened: popupOpen

  function activateAction() {
    if (selectedAction === 0) refresh()
    else review()
  }

  implicitWidth: vertical ? barSize : button.implicitWidth
  implicitHeight: vertical ? button.implicitHeight : barSize

  onBarChanged: Qt.callLater(root.configureService)
  onSettingsChanged: Qt.callLater(root.configureService)
  onHostBarConfigChanged: Qt.callLater(root.configureService)
  onGuardServiceChanged: Qt.callLater(root.configureService)
  onPopupOpenChanged: if (popupOpen) {
    selectedAction = 1
    refresh()
  }
  Component.onCompleted: Qt.callLater(root.configureService)

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰒃"
    foreground: root.shieldColor
    slotSize: Style.bar.statusSlot
    tooltipText: root.guardSummary

    onPressed: function(buttonCode) {
      if (buttonCode === Qt.MiddleButton || buttonCode === Qt.RightButton) root.refresh()
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: popup
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.popupOpen
    focusTarget: keyCatcher
    contentWidth: popup.fittedContentWidth(Style.space(390))
    contentHeight: popup.fittedContentHeight(content.implicitHeight, Style.space(620))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onMoveRequested: function(dx, dy) {
        if (dx !== 0 || dy !== 0) root.selectedAction = root.selectedAction === 0 ? 1 : 0
      }
      onTabRequested: function(direction) {
        root.selectedAction = root.selectedAction === 0 ? 1 : 0
      }
      onActivateRequested: root.activateAction()
      onTextKey: function(text) {
        if (text === "r" || text === "R") root.refresh()
      }

      Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: content
          width: parent.width
          spacing: Style.space(12)

          PanelHero {
            width: parent.width
            title: "Omaudit Status"
            meta: root.guardSummary
            detail: root.guardService && root.guardService.scanning ? "Scanning" : "Review"
            foreground: root.foreground
            fontFamily: root.fontFamily
            iconOpacity: root.guardTone === "dim" ? 0.55 : 1.0
            iconComponent: Component {
              Text {
                text: "󰒃"
                textFormat: Text.PlainText
                color: root.shieldColor
                font.family: root.fontFamily
                font.pixelSize: Style.font.display
              }
            }
          }

          Text {
            width: parent.width
            text: root.statusDocument.installed === false
              ? "Omaudit is missing. Install Omaudit v0.1.0 or newer using its official instructions, then refresh."
              : (root.guardState === "error"
                ? "Capability and risk review is unavailable. Findings require human review."
              : "Capability and risk review only — changes require human review."
              )
            textFormat: Text.PlainText
            color: Qt.darker(root.foreground, 1.35)
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.Wrap
          }

          Row {
            width: parent.width
            spacing: Style.space(12)

            Repeater {
              model: [
                { label: "Plugins", value: root.totals.plugins },
                { label: "Changed", value: root.totals.changed },
                { label: "Untracked", value: root.totals.notTracked },
                { label: "Composition", value: root.totals.compositionRisks },
                { label: "Worst", value: root.statusDocument.worstGrade || "—" }
              ]

              Column {
                required property var modelData
                width: (content.width - Style.space(48)) / 5
                spacing: Style.space(2)

                Text {
                  anchors.horizontalCenter: parent.horizontalCenter
                  text: parent.modelData.value
                  textFormat: Text.PlainText
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.subtitle
                  font.bold: true
                }
                Text {
                  anchors.horizontalCenter: parent.horizontalCenter
                  text: parent.modelData.label
                  textFormat: Text.PlainText
                  color: Qt.darker(root.foreground, 1.5)
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
              }
            }
          }

          Text {
            width: parent.width
            text: "Scanned " + StatusModel.scanTime(root.statusDocument)
            textFormat: Text.PlainText
            color: Qt.darker(root.foreground, 1.55)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            elide: Text.ElideRight
          }

          PanelSeparator {
            visible: root.visiblePlugins.length > 0
            foreground: root.foreground
          }

          Column {
            width: parent.width
            spacing: Style.space(6)
            visible: root.visiblePlugins.length > 0

            Repeater {
              model: root.visiblePlugins

              BorderSurface {
                required property var modelData
                width: parent.width
                implicitHeight: pluginLabels.implicitHeight + Style.space(10)
                radius: Style.cornerRadius
                color: "transparent"
                borderSpec: Border.controlSpec("normal", root.foreground, Color.accent)

                Column {
                  id: pluginLabels
                  anchors.left: parent.left
                  anchors.right: parent.right
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.leftMargin: Style.space(8)
                  anchors.rightMargin: Style.space(8)
                  spacing: Style.space(2)

                  Text {
                    width: parent.width
                    text: (modelData.name || modelData.id) + (modelData.grade ? "  ·  Grade " + modelData.grade : "")
                    textFormat: Text.PlainText
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                    font.bold: modelData.status !== "unchanged"
                    elide: Text.ElideRight
                  }
                  Text {
                    width: parent.width
                    text: modelData.composition.length > 0
                      ? "Composition risk needs review"
                      : (modelData.status === "changed" ? "Capability drift"
                        : (modelData.status === "not-tracked" ? "Baseline review needed" : "Unchanged"))
                    textFormat: Text.PlainText
                    color: modelData.status === "unchanged"
                      ? Qt.darker(root.foreground, 1.5) : root.shieldColor
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    elide: Text.ElideRight
                  }
                }
              }
            }
          }

          Text {
            visible: root.totals.plugins > root.visiblePlugins.length
            width: parent.width
            text: "+ " + (root.totals.plugins - root.visiblePlugins.length) + " more plugins"
            textFormat: Text.PlainText
            color: Qt.darker(root.foreground, 1.5)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Row {
            anchors.right: parent.right
            spacing: Style.space(8)

            Button {
              text: "Refresh"
              iconText: "󰑐"
              foreground: root.foreground
              hasCursor: root.selectedAction === 0
              focusable: true
              enabled: !(root.guardService && root.guardService.scanning)
              onHovered: function(isHovered) { if (isHovered) root.selectedAction = 0 }
              onClicked: root.refresh()
            }

            Button {
              text: "Review in terminal"
              iconText: "󰆍"
              foreground: root.foreground
              hasCursor: root.selectedAction === 1
              focusable: true
              onHovered: function(isHovered) { if (isHovered) root.selectedAction = 1 }
              onClicked: root.review()
            }
          }
        }
      }
    }
  }
}
