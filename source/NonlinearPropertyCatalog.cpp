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

#include "NonlinearPropertyCatalog.h"

#include "DampingFactory.h"
#include "ModulusFactory.h"

#include <QDataStream>
#include <QDebug>
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QStandardPaths>

NonlinearPropertyCatalog::NonlinearPropertyCatalog() {
  _modulusFactory = new ModulusFactory;
  _dampingFactory = new DampingFactory;

  loadBuiltinCurves();

  _fileName =
      QStandardPaths::writableLocation(QStandardPaths::AppDataLocation) +
      "/nonlinearCurves";

  QFile file(_fileName);
  if (file.exists() && file.open(QIODevice::ReadOnly)) {
    QDataStream in(&file);
    in >> *(_modulusFactory) >> *(_dampingFactory);
  }
}

NonlinearPropertyCatalog::~NonlinearPropertyCatalog() {
  delete _modulusFactory;
  delete _dampingFactory;
}

auto NonlinearPropertyCatalog::modulusFactory() -> ModulusFactory * {
  return _modulusFactory;
}

auto NonlinearPropertyCatalog::dampingFactory() -> DampingFactory * {
  return _dampingFactory;
}

auto NonlinearPropertyCatalog::save() const -> bool {
  const QString dest =
      QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);
  QDir dir;

  if (!dir.exists(dest) && !dir.mkpath(dest)) {
    return false;
  }

  QFile file(_fileName);
  if (file.open(QIODevice::WriteOnly)) {
    QDataStream out(&file);
    out << *(_modulusFactory) << *(_dampingFactory);
  } else {
    return false;
  }

  return true;
}

void NonlinearPropertyCatalog::loadBuiltinCurves() {
  QFile file(":/data/curve_gd_marche3.json");
  if (!file.open(QIODevice::ReadOnly))
    return;

  const QJsonObject json = QJsonDocument::fromJson(file.readAll()).object();
  _modulusFactory->addBuiltinModels(json["modulus"].toArray());
  _dampingFactory->addBuiltinModels(json["damping"].toArray());
}

auto NonlinearPropertyCatalog::exportCurves(const QString &fileName,
                                            QString *error) const -> bool {
  QJsonObject json;
  json["format"] = "strata-nonlinear-curves";
  json["version"] = 1;
  json["modulus"] = _modulusFactory->toJson();
  json["damping"] = _dampingFactory->toJson();

  QFile file(fileName);
  if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
    if (error)
      *error = file.errorString();
    return false;
  }
  file.write(QJsonDocument(json).toJson(QJsonDocument::Indented));
  return true;
}

auto NonlinearPropertyCatalog::importCurves(const QString &fileName,
                                            int *modulusCount,
                                            int *dampingCount, QString *error)
    -> bool {
  QFile file(fileName);
  if (!file.open(QIODevice::ReadOnly)) {
    if (error)
      *error = file.errorString();
    return false;
  }
  const QByteArray bytes = file.readAll();

  QJsonObject modulus;
  QJsonObject damping;

  QJsonParseError parseError;
  const QJsonDocument doc = QJsonDocument::fromJson(bytes, &parseError);
  if (parseError.error == QJsonParseError::NoError && doc.isObject()) {
    const QJsonObject json = doc.object();
    modulus = json["modulus"].toObject();
    damping = json["damping"].toObject();
    if (!json.contains("modulus") && !json.contains("damping")) {
      if (error)
        *error = QObject::tr("The file does not contain nonlinear curves.");
      return false;
    }
  } else {
    // Try the binary database used by Strata (nonlinearCurves)
    ModulusFactory mf;
    DampingFactory df;
    QDataStream in(bytes);
    in >> mf >> df;
    if (in.status() != QDataStream::Ok) {
      if (error)
        *error = QObject::tr("The file is not a valid curve database.");
      return false;
    }
    modulus = mf.toJson();
    damping = df.toJson();
  }

  const int nm = _modulusFactory->importModels(modulus);
  const int nd = _dampingFactory->importModels(damping);
  if (modulusCount)
    *modulusCount = nm;
  if (dampingCount)
    *dampingCount = nd;

  save();
  return true;
}
