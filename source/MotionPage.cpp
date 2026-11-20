////////////////////////////////////////////////////////////////////////////////
//
// This file is part of Strata.
//
// Strata is free software: you can redistribute it and/or modify it under the
// terms of the GNU General Public License as published by the Free Software
// Foundation, either version 3 of the License, or (at your option) any later
// version.
//
// Strata is distributed in the hope that it will be useful, but WITHOUT ANY
// WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
// FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
// details.
//
// You should have received a copy of the GNU General Public License along with
// Strata.  If not, see <http://www.gnu.org/licenses/>.
//
// Copyright 2010-2018 Albert Kottke
//
////////////////////////////////////////////////////////////////////////////////

#include "MotionPage.h"

#include "CompatibleRvtMotion.h"
#include "CompatibleRvtMotionDialog.h"
#include "DepthComboBox.h"
#include "MotionLibrary.h"
#include "MotionTypeDelegate.h"
#include "MyTableView.h"
#include "RvtMotion.h"
#include "RvtMotionDialog.h"
#include "SiteResponseModel.h"
#include "SoilProfile.h"
#include "SourceTheoryRvtMotion.h"
#include "SourceTheoryRvtMotionDialog.h"
#include "TimeSeriesMotion.h"
#include "TimeSeriesMotionDialog.h"

#include <QBuffer>
#include <QDataStream>
#include <QDebug>
#include <QDoubleValidator>
#include <QFileDialog>
#include <QFormLayout>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QInputDialog>
#include <QLabel>
#include <QMessageBox>
#include <QProgressDialog>
#include <QPushButton>
#include <QSettings>
#include <QStandardPaths>
#include <QTableView>
#include <QVBoxLayout>

MotionPage::MotionPage(QWidget *parent, Qt::WindowFlags f)
    : AbstractPage(parent, f), _readOnly(false) {
  // Set the layout of the widget
  auto *layout = new QVBoxLayout;
  layout->addWidget(createInputLocationGroupBox());
  layout->addWidget(createMotionsTableGroupBox(), 1);

  setLayout(layout);
}

void MotionPage::setModel(SiteResponseModel *model) {
  _motionLibrary = model->motionLibrary();

  _depthComboBox->setDepth(model->siteProfile()->inputDepth());
  connect(_depthComboBox, &DepthComboBox::depthChanged, model->siteProfile(),
          &SoilProfile::setInputDepth);

  _tableView->setModel(_motionLibrary);
  connect(_tableView->selectionModel(), &QItemSelectionModel::selectionChanged,
          this, &MotionPage::updateButtons);
  _tableView->resizeColumnsToContents();
  _tableView->resizeRowsToContents();

  setApproach(_motionLibrary->approach());
  connect(_motionLibrary, &MotionLibrary::approachChanged, this,
          &MotionPage::setApproach);
}

void MotionPage::setReadOnly(bool readOnly) {
  _readOnly = readOnly;
  _depthComboBox->setDisabled(readOnly);
  _tableView->setReadOnly(readOnly);

  _addButton->setHidden(readOnly);
  _removeButton->setHidden(readOnly);
  _importButton->setHidden(readOnly);
  _addMultipleButton->setHidden(readOnly);
  _editButton->setText(readOnly ? tr("View") : tr("Edit"));
}

void MotionPage::setApproach(int i) {
  _addMultipleButton->setEnabled(i == MotionLibrary::TimeSeries);
  _tableView->setColumnHidden(MotionLibrary::ScaleColumn,
                              i == MotionLibrary::RandomVibrationTheory);
}

auto MotionPage::createInputLocationGroupBox() -> QGroupBox * {
  auto *layout = new QHBoxLayout;

  layout->addWidget(
      new QLabel(tr("Specify the location to input the motion(s):")));

  _depthComboBox = new DepthComboBox;
  layout->addWidget(_depthComboBox);
  layout->addStretch(1);

  _inputLocationGroupBox = new QGroupBox(tr("Motion Input Location"));
  _inputLocationGroupBox->setLayout(layout);

  return _inputLocationGroupBox;
}

auto MotionPage::createMotionsTableGroupBox() -> QGroupBox * {
  auto *layout = new QVBoxLayout;
  // Create the buttons
  auto *buttonRow = new QHBoxLayout;

  _addButton = new QPushButton(QIcon(":/images/list-add.svg"), tr("Add"));
  connect(_addButton, &QPushButton::clicked, this, &MotionPage::add);
  buttonRow->addWidget(_addButton);

  _addMultipleButton = new QPushButton(QIcon(":/images/document-import.svg"),
                                       tr("Add Files..."));
  _addMultipleButton->setToolTip(
      tr("Load several acceleration time series at once (AT2, ESM/ITACA)"));
  connect(_addMultipleButton, &QPushButton::clicked, this,
          &MotionPage::addMultiple);
  buttonRow->addWidget(_addMultipleButton);

  _removeButton =
      new QPushButton(QIcon(":/images/list-remove.svg"), tr("Remove"));
  _removeButton->setEnabled(false);
  connect(_removeButton, &QPushButton::clicked, this, &MotionPage::remove);
  buttonRow->addWidget(_removeButton);

  _editButton = new QPushButton;
  _editButton->setEnabled(false);
  connect(_editButton, &QPushButton::clicked, this, &MotionPage::edit);
  buttonRow->addWidget(_editButton);

  _importButton =
      new QPushButton(QIcon(":/images/document-import.svg"), tr("Load Suite"));
  connect(_importButton, &QPushButton::clicked, this, &MotionPage::importSuite);

  buttonRow->addStretch(1);
  buttonRow->addWidget(_importButton);

  layout->addLayout(buttonRow);

  // Create table
  _tableView = new MyTableView(this);
  _tableView->setSelectionMode(QAbstractItemView::ContiguousSelection);
  _tableView->setEditTriggers(QAbstractItemView::NoEditTriggers);
  _tableView->setItemDelegateForColumn(2, new MotionTypeDelegate);

  connect(_tableView, &QTableView::doubleClicked, this, &MotionPage::edit);
  layout->addWidget(_tableView, 1);

  // Form the groupbox
  _motionsTableGroupBox = new QGroupBox(tr("Input Motions"));
  _motionsTableGroupBox->setLayout(layout);

  return _motionsTableGroupBox;
}

void MotionPage::add() {
  QDialog *dialog = nullptr;
  AbstractMotion *motion = nullptr;

  switch (_motionLibrary->approach()) {
  case MotionLibrary::TimeSeries: {
    auto *_motion = new TimeSeriesMotion(_motionLibrary);
    _motion->setSaveData(_motionLibrary->saveData());

    dialog = (QDialog *)(new TimeSeriesMotionDialog(_motion, _readOnly, this));
    motion = (AbstractMotion *)_motion;
    break;
  }
  case MotionLibrary::RandomVibrationTheory: {
    // Prompt for type of motions
    QStringList items = QStringList() << tr("User Defined FAS")
                                      << tr("Response Spectrum Compatible")
                                      << tr("Seismological Source Theory");
    bool ok;
    QString item = QInputDialog::getItem(
        this, tr("RVT Motion Type"),
        tr("Select method for defining RVT motion:"), items, 0, false, &ok);

    if (!ok) {
      return;
    }

    switch (items.indexOf(item)) {
    case 0: {
      // User defined FAS
      auto *_motion = new RvtMotion(_motionLibrary);
      dialog = (QDialog *)(new RvtMotionDialog(_motion, _readOnly, this));
      motion = (AbstractMotion *)_motion;
      break;
    }
    case 1: {
      // Response Spectrum Compatible
      auto *_motion = new CompatibleRvtMotion(_motionLibrary);
      dialog =
          (QDialog *)(new CompatibleRvtMotionDialog(_motion, _readOnly, this));
      motion = (AbstractMotion *)_motion;
      break;
    }
    case 2: {
      // User defined FAS
      auto *_motion = new SourceTheoryRvtMotion(_motionLibrary);
      dialog = (QDialog *)(new SourceTheoryRvtMotionDialog(_motion, _readOnly,
                                                           this));
      motion = (AbstractMotion *)_motion;
      break;
    }
    }
  }
  }

  if (dialog->exec()) {
    _motionLibrary->addMotion(motion);
    _tableView->resizeColumnsToContents();
    _tableView->resizeRowsToContents();
  } else {
    // FIXME deleting the motions causes a segfault!
    motion->deleteLater();
  }

  delete dialog;
}

void MotionPage::remove() {
  QModelIndexList selectedRows = _tableView->selectionModel()->selectedRows();
  _motionLibrary->removeRows(selectedRows.first().row(), selectedRows.size());
}

static void reportFailedFiles(QWidget *parent, const QStringList &failed) {
  if (failed.isEmpty())
    return;
  QStringList names;
  for (const QString &f : failed)
    names << QFileInfo(f).fileName();
  QMessageBox::warning(
      parent, QObject::tr("Load motions - Strata"),
      QObject::tr("%1 file(s) could not be loaded automatically. Add them "
                  "one at a time with \"Add\" to set the format by hand:\n\n%2")
          .arg(failed.size())
          .arg(names.join("\n")));
}

void MotionPage::addMultiple() {
  if (_motionLibrary->approach() != MotionLibrary::TimeSeries)
    return;

  QSettings settings;
  const QStringList fileNames = QFileDialog::getOpenFileNames(
      this, tr("Select acceleration time series... - Strata"),
      settings
          .value("motionDirectory", QStandardPaths::writableLocation(
                                        QStandardPaths::DocumentsLocation))
          .toString(),
      tr("Time series (*.AT2 *.at2 *.ASC *.asc *.txt *.TXT);;All files (*)"));

  if (fileNames.isEmpty())
    return;

  settings.setValue("motionDirectory",
                    QFileInfo(fileNames.first()).absolutePath());

  QProgressDialog progressDialog(tr("Loading motions..."), tr("Abort"), 0,
                                 fileNames.size(), this);
  progressDialog.setWindowModality(Qt::WindowModal);

  QStringList failed;
  int i = 0;
  for (const QString &fileName : fileNames) {
    if (progressDialog.wasCanceled())
      break;
    bool ok = false;
    auto *tsm = new TimeSeriesMotion(fileName, 1.0, AbstractMotion::Outcrop,
                                     &ok, _motionLibrary);
    if (ok) {
      tsm->setSaveData(_motionLibrary->saveData());
      _motionLibrary->addMotion(tsm);
    } else {
      tsm->deleteLater();
      failed << fileName;
    }
    progressDialog.setValue(++i);
  }

  _tableView->resizeColumnsToContents();
  _tableView->resizeRowsToContents();
  reportFailedFiles(this, failed);
}

void MotionPage::importSuite() {
  QSettings settings;
  // Prompt for the file to load
  QString fileName = QFileDialog::getOpenFileName(
      this, tr("Select suite file... - Strata"),
      settings
          .value("suiteDirectory", QStandardPaths::writableLocation(
                                       QStandardPaths::DocumentsLocation))
          .toString(),
      "Strata Suite File (*.csv)");

  if (!fileName.isEmpty()) {
    QFileInfo fileInfo(fileName);

    // Save the path
    settings.setValue("suiteDirectory", fileInfo.filePath());

    // Load the file
    QFile file(fileName);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
      qWarning() << "Unable to open file:" << fileName;
      return;
    }

    // Clear the previous motions
    const int rowCount = _motionLibrary->rowCount();

    if (rowCount)
      _motionLibrary->removeRows(0, rowCount);

    // Count the number of lines
    QTextStream stream(&file);
    QStringList lines;
    while (!stream.atEnd()) {
      const QString line = stream.readLine().trimmed();
      if (!line.isEmpty() && !line.startsWith("#"))
        lines << line;
    }
    QStringList failed;

    // Load each of the filename/scale pairs in a map
    QProgressDialog progressDialog(tr("Loading motion suite..."), tr("Abort"),
                                   1, lines.size(), this);
    progressDialog.setWindowModality(Qt::WindowModal);

    for (const QString &line : lines) {
      if (progressDialog.wasCanceled())
        break;
      QStringList args = line.split(",");
      if (args.size() < 1 || args.size() > 3) {
        qCritical() << tr("Invalid file format on line:") << line;
        return;
      }

      QString _fileName = args.takeFirst().trimmed();
      // Paths in the suite file may be relative to the suite file
      if (QFileInfo(_fileName).isRelative())
        _fileName = fileInfo.absoluteDir().filePath(_fileName);

      double scale = 1;
      auto type = AbstractMotion::Outcrop;
      bool ok;

      if (args.size() > 0) {
        scale = args.at(0).toDouble(&ok);
        if (!ok) {
          qCritical() << "Error converting" << args.at(0) << "to a number!\n"
                      << "Assuming a scale of 1.0.";
          scale = 1;
        }
      }

      if (args.size() > 1) {
        type = AbstractMotion::variantToType(args.at(1), &ok);
        if (!ok) {
          qCritical() << "Unknown type specified:" << args.at(1)
                      << ". Valid options are 'Outcrop'"
                      << "\nAssuming 'Outcrop'";
          type = AbstractMotion::Outcrop;
        }
      }

      if (_motionLibrary->approach() == MotionLibrary::TimeSeries) {
        // Load the motion
        auto *tsm = new TimeSeriesMotion(_fileName, scale, type, &ok);
        if (ok) {
          tsm->setSaveData(_motionLibrary->saveData());
          _motionLibrary->addMotion(tsm);
        } else {
          tsm->deleteLater();
          failed << _fileName;
        }
      } else {
        auto *arm = loadRvtMotionFromTextFile(_fileName, scale);
        if (arm)
          _motionLibrary->addMotion(arm);
        else
          failed << _fileName;
      }
      progressDialog.setValue(_motionLibrary->rowCount());
    }
    reportFailedFiles(this, failed);
  }

  _tableView->resizeColumnsToContents();
  _tableView->resizeRowsToContents();
}

void MotionPage::edit() {
  const QModelIndex &index = _tableView->currentIndex();
  AbstractMotion *motion = _motionLibrary->motionAt(index.row());

  // Buffer to save the state of the motion
  QBuffer buffer;
  buffer.open(QBuffer::ReadWrite);
  QDataStream dataStream(&buffer);

  // Save the current state of the motion
  dataStream << motion;

  QDialog *dialog = nullptr;

  if (auto *tsm = qobject_cast<TimeSeriesMotion *>(motion)) {
    dialog = new TimeSeriesMotionDialog(tsm, _readOnly, this);
  } else if (auto *rm = qobject_cast<RvtMotion *>(motion)) {
    dialog = new RvtMotionDialog(rm, _readOnly, this);
  } else if (auto *crm = qobject_cast<CompatibleRvtMotion *>(motion)) {
    dialog = new CompatibleRvtMotionDialog(crm, _readOnly, this);
  } else if (auto *_motion = qobject_cast<SourceTheoryRvtMotion *>(motion)) {
    dialog = new SourceTheoryRvtMotionDialog(_motion, _readOnly, this);
  }

  if (!dialog->exec()) {
    buffer.seek(0);
    // Revert to the previous state
    dataStream >> motion;
    _motionLibrary->updateRow(index.row());
  }

  dialog->deleteLater();
}

void MotionPage::updateButtons() {
  auto rows = _tableView->selectionModel()->selectedRows();
  _removeButton->setEnabled(rows.length() > 0);
  _editButton->setEnabled(rows.length() == 1);
}
