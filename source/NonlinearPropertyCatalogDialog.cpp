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

#include "NonlinearPropertyCatalogDialog.h"

#include "DampingFactory.h"
#include "ModulusFactory.h"
#include "MyTableView.h"
#include "NonlinearProperty.h"
#include "NonlinearPropertyFactoryGroupBox.h"

#include <QDialogButtonBox>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QMessageBox>
#include <QSettings>
#include <QGridLayout>
#include <QLabel>
#include <QTableView>

#include <QDebug>

NonlinearPropertyCatalogDialog::NonlinearPropertyCatalogDialog(
    NonlinearPropertyCatalog *catalog, QWidget *parent, Qt::WindowFlags f)
    : QDialog(parent, f), _catalog(catalog) {
  auto *layout = new QGridLayout;

  // Shear modulus list
  auto *modulus = new NonlinearPropertyFactoryGroupBox(
      catalog->modulusFactory(), tr("Shear Modulus Reduction Models"), this);

  connect(modulus, &NonlinearPropertyFactoryGroupBox::nlPropertyChanged, this,
          &NonlinearPropertyCatalogDialog::setDataModel);

  layout->addWidget(modulus, 0, 0);

  // Damping list
  auto *damping = new NonlinearPropertyFactoryGroupBox(
      catalog->dampingFactory(), tr("Damping Models"), this);

  connect(damping, &NonlinearPropertyFactoryGroupBox::nlPropertyChanged, this,
          &NonlinearPropertyCatalogDialog::setDataModel);

  layout->addWidget(damping, 1, 0);

  connect(modulus, &NonlinearPropertyFactoryGroupBox::nlPropertyChanged,
          damping, &NonlinearPropertyFactoryGroupBox::clearSelection);
  connect(damping, &NonlinearPropertyFactoryGroupBox::nlPropertyChanged,
          modulus, &NonlinearPropertyFactoryGroupBox::clearSelection);

  // Data group box
  _dataGroupBox = new TableGroupBox(tr("Nonlinear Curve Data"));

  layout->addWidget(_dataGroupBox, 0, 1, 2, 2);

  // Information regard permanent models
  layout->addWidget(
      new QLabel(tr("Gray background indicates immutable model.")), 2, 0);

  // Button box
  auto *buttonBox =
      new QDialogButtonBox(QDialogButtonBox::Ok, Qt::Horizontal, this);
  connect(buttonBox, &QDialogButtonBox::accepted, this,
          &NonlinearPropertyCatalogDialog::accept);

  auto *exportButton =
      buttonBox->addButton(tr("Export curves..."), QDialogButtonBox::ActionRole);
  exportButton->setToolTip(
      tr("Save the user defined curves to a file, to be imported in another "
         "installation of Strata."));
  connect(exportButton, &QPushButton::clicked, this,
          &NonlinearPropertyCatalogDialog::exportCurves);

  auto *importButton =
      buttonBox->addButton(tr("Import curves..."), QDialogButtonBox::ActionRole);
  importButton->setToolTip(
      tr("Add the curves saved in a file. Curves with an existing name are "
         "skipped."));
  connect(importButton, &QPushButton::clicked, this,
          &NonlinearPropertyCatalogDialog::importCurves);

  layout->addWidget(buttonBox, 2, 1);

  setLayout(layout);
  setWindowTitle(tr("Nonlinear Property Manager - Strata"));

  // Select the first index
  modulus->selectRow(0);
}

void NonlinearPropertyCatalogDialog::setDataModel(NonlinearProperty *np,
                                                  bool readOnly) {
  _dataGroupBox->setModel(np);
  _dataGroupBox->setReadOnly(readOnly);
}

void NonlinearPropertyCatalogDialog::exportCurves() {
  QSettings settings;
  QString fileName = QFileDialog::getSaveFileName(
      this, tr("Export curves - Strata"),
      settings.value("nlCurvesDir", QDir::homePath()).toString() +
          "/strata-curves.json",
      tr("Strata curves (*.json)"));
  if (fileName.isEmpty())
    return;

  if (!fileName.endsWith(".json", Qt::CaseInsensitive))
    fileName += ".json";
  settings.setValue("nlCurvesDir", QFileInfo(fileName).absolutePath());

  // Save the current state first
  _catalog->save();

  QString error;
  if (_catalog->exportCurves(fileName, &error)) {
    QMessageBox::information(
        this, tr("Export curves - Strata"),
        tr("User defined curves saved to:\n%1").arg(fileName));
  } else {
    QMessageBox::warning(this, tr("Export curves - Strata"),
                         tr("Unable to save the file:\n%1").arg(error));
  }
}

void NonlinearPropertyCatalogDialog::importCurves() {
  QSettings settings;
  const QString fileName = QFileDialog::getOpenFileName(
      this, tr("Import curves - Strata"),
      settings.value("nlCurvesDir", QDir::homePath()).toString(),
      tr("Strata curves (*.json);;Strata curve database (nonlinearCurves*);;"
         "All files (*)"));
  if (fileName.isEmpty())
    return;

  settings.setValue("nlCurvesDir", QFileInfo(fileName).absolutePath());

  int nm = 0;
  int nd = 0;
  QString error;
  if (_catalog->importCurves(fileName, &nm, &nd, &error)) {
    QMessageBox::information(
        this, tr("Import curves - Strata"),
        tr("Imported %1 shear modulus reduction curve(s) and %2 damping "
           "curve(s).\nCurves with a name already present were skipped.")
            .arg(nm)
            .arg(nd));
  } else {
    QMessageBox::warning(this, tr("Import curves - Strata"),
                         tr("Unable to import the file:\n%1").arg(error));
  }
}
