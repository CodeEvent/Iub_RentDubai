import NFCPassportReader
import UIKit

/// Reads the passport chip over NFC -- the actual BAC handshake, key
/// derivation, and DG1/DG2 parsing (including JPEG2000 decoding, which
/// stock iOS/Android image APIs can't do) are handled by the open-source
/// NFCPassportReader package (github.com/AndyQ/NFCPassportReader, MIT),
/// the same category of dependency as JMRTD on the Android side of this
/// project -- there's no reason to hand-roll ICAO 9303 crypto when a
/// mature library already does it.
///
/// `PassportReader.readPassport(mrzKey:tags:...)`'s signature and
/// `NFCPassportModel`'s properties below were checked against the actual
/// tagged 2.3.3 source (github.com/AndyQ/NFCPassportReader), not
/// guessed -- it's `async throws`, not completion-handler based. The MRZ
/// composite-key algorithm (computeMRZKey below) is the standardized
/// ICAO 9303 one and doesn't depend on the library at all.
struct PassportReadResult {
    let documentNumber: String
    let firstName: String
    let lastName: String
    let chipPhoto: UIImage?
}

enum PassportNFCError: LocalizedError {
    case noPhotoOnChip
    case readFailed(String)

    var errorDescription: String? {
        switch self {
        case .noPhotoOnChip: return "This passport's chip didn't contain a photo to match against."
        case .readFailed(let message): return message
        }
    }
}

final class PassportNFCService {
    private let reader = PassportReader()

    func readPassport(passportNumber: String, dateOfBirth: Date, dateOfExpiry: Date) async throws -> PassportReadResult {
        let mrzKey = Self.computeMRZKey(
            passportNumber: passportNumber,
            dateOfBirth: Self.mrzDate(dateOfBirth),
            dateOfExpiry: Self.mrzDate(dateOfExpiry)
        )

        let model: NFCPassportModel
        do {
            model = try await reader.readPassport(mrzKey: mrzKey, tags: [.COM, .DG1, .DG2])
        } catch {
            throw PassportNFCError.readFailed(error.localizedDescription)
        }

        return PassportReadResult(
            documentNumber: model.documentNumber,
            firstName: model.firstName,
            lastName: model.lastName,
            chipPhoto: model.passportImage
        )
    }

    /// ICAO 9303 MRZ composite check-digit algorithm (7/3/1 weighting) --
    /// standardized, not library-specific. `dateOfBirth`/`dateOfExpiry`
    /// must already be in MRZ's YYMMDD format (see `mrzDate` below).
    static func computeMRZKey(passportNumber: String, dateOfBirth: String, dateOfExpiry: String) -> String {
        let paddedNumber = passportNumber
            .uppercased()
            .padding(toLength: 9, withPad: "<", startingAt: 0)
        return paddedNumber + String(checkDigit(paddedNumber))
            + dateOfBirth + String(checkDigit(dateOfBirth))
            + dateOfExpiry + String(checkDigit(dateOfExpiry))
    }

    static func mrzDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyMMdd"
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter.string(from: date)
    }

    private static func checkDigit(_ input: String) -> Int {
        let weights = [7, 3, 1]
        var sum = 0
        for (index, char) in input.enumerated() {
            let value: Int
            if let digit = char.wholeNumberValue, char.isNumber {
                value = digit
            } else if char == "<" {
                value = 0
            } else if char.isLetter, let ascii = char.uppercased().unicodeScalars.first?.value {
                value = Int(ascii) - 55 // 'A' (65) -> 10, ... 'Z' (90) -> 35
            } else {
                value = 0
            }
            sum += value * weights[index % 3]
        }
        return sum % 10
    }
}
